"""Short-lived authenticated TLS 1.3 framed echo and HTTP/3 POST baseline."""

import asyncio
import contextlib
import datetime
import hashlib
import hmac
import ipaddress
import json
import os
import socket
import ssl
import struct
import sys
import tempfile
import time
from pathlib import Path

from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.asyncio.server import QuicServer
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated, HandshakeCompleted
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from pprl_core.qlog import SafeLogger, read_qlog


def certificate(address: str, directory: Path) -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "NetSpectra ephemeral lab")]
    )
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address(address))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    for filename, content in [
        ("cert.pem", pem),
        (
            "key.pem",
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        ),
    ]:
        path = directory / filename
        with path.open("xb") as stream:
            stream.write(content)
        path.chmod(0o600)
    return pem.decode()


def echo(data: bytes, config: dict) -> bytes:
    if len(data) > 4096:
        raise ValueError("invalid_frame")
    message = json.loads(data)
    if not isinstance(message.get("token"), str) or not hmac.compare_digest(
        message["token"], config["token"]
    ):
        raise ValueError("invalid_token")
    if not 1 <= len(bytes.fromhex(message["payload"])) <= 512:
        raise ValueError("invalid_payload")
    return json.dumps(
        {"payload": message["payload"], "backend": config["node_id"]}
    ).encode()


class HTTP3(QuicConnectionProtocol):
    def __init__(self, *args, lab_config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.http = H3Connection(self._quic)
        self.lab = lab_config
        self.bodies = {}
        self.headers = {}
        self.pending = {}
        self.handshake = False

    def datagram_received(self, data, addr):
        if self.lab and addr[0] not in self.lab["peers"]:
            return
        super().datagram_received(data, addr)

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            self.handshake = True
        if isinstance(event, ConnectionTerminated):
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ConnectionError("quic_connection_closed"))
        for item in self.http.handle_event(event):
            if not isinstance(item, HeadersReceived | DataReceived):
                continue
            stream = item.stream_id
            if stream not in self.bodies and len(self.bodies) >= 16:
                self.close(error_code=0x107)
                return
            if isinstance(item, HeadersReceived):
                if sum(len(k) + len(v) for k, v in item.headers) > 4096:
                    self.close(error_code=0x107)
                    return
                self.headers[stream] = dict(item.headers)
            else:
                self.bodies[stream] = self.bodies.get(stream, b"") + item.data
                if len(self.bodies[stream]) > 4096:
                    self.close(error_code=0x107)
                    return
            if item.stream_ended:
                body = self.bodies.pop(stream, b"")
                headers = self.headers.pop(stream, {})
                if self.lab:
                    try:
                        if (
                            headers.get(b":method") != b"POST"
                            or headers.get(b":path") != b"/echo"
                        ):
                            raise ValueError("invalid_request")
                        response = echo(body, self.lab)
                        status = b"200"
                    except (ValueError, KeyError, TypeError):
                        response, status = b"{}", b"403"
                    self.http.send_headers(
                        stream,
                        [(b":status", status), (b"content-type", b"application/json")],
                    )
                    self.http.send_data(stream, response, end_stream=True)
                    self.transmit()
                elif stream in self.pending:
                    future = self.pending.pop(stream)
                    if not future.done():
                        if headers.get(b":status") == b"200":
                            future.set_result(body)
                        else:
                            future.set_exception(ValueError("http3_response_error"))

    async def request(self, data: bytes) -> bytes:
        stream = self._quic.get_next_available_stream_id()
        future = asyncio.get_running_loop().create_future()
        self.pending[stream] = future
        self.http.send_headers(
            stream,
            [
                (b":method", b"POST"),
                (b":scheme", b"https"),
                (b":authority", b"netspectra.lab"),
                (b":path", b"/echo"),
                (b"content-type", b"application/json"),
            ],
        )
        self.http.send_data(stream, data, end_stream=True)
        self.transmit()
        return await future


class RestrictedServer(QuicServer):
    """Discard unselected peers before allocating QUIC connection state."""

    def __init__(self, *args, peers, **kwargs):
        super().__init__(*args, **kwargs)
        self.peers = peers

    def datagram_received(self, data, addr):
        if addr[0] not in self.peers:
            return
        if len(set(self._protocols.values())) >= 16:
            return
        super().datagram_received(data, addr)


async def read_frame(reader):
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    if not 1 <= size <= 4096:
        raise ValueError("invalid_frame")
    return await reader.readexactly(size)


async def server(config: dict, directory: Path) -> dict:
    pem = certificate(config["public_address"], directory)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()

    def watch():
        os.read(sys.stdin.fileno(), 1)
        loop.call_soon_threadsafe(stopped.set)

    import threading

    threading.Thread(target=watch, daemon=True).start()
    tasks = set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            peer = writer.get_extra_info("peername")
            if not peer or peer[0] not in config["peers"] or len(tasks) > 8:
                return
            async with asyncio.timeout(5):
                response = echo(await read_frame(reader), config)
                writer.write(struct.pack("!I", len(response)) + response)
                await writer.drain()
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            TimeoutError,
            asyncio.IncompleteReadError,
        ):
            pass
        finally:
            writer.close()
            with contextlib.suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 1)
            tasks.discard(task)

    if config["protocol"] == "tls":
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(directory / "cert.pem", directory / "key.pem")
        # Preserve occupied listeners and permit only TCP TIME_WAIT reuse.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if os.name == "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((config["bind_address"], config["port"]))
            sock.listen(8)
            sock.setblocking(False)
            listener = await asyncio.start_server(
                handle, sock=sock, ssl=context, ssl_handshake_timeout=5
            )
        except BaseException:
            sock.close()
            raise
    else:
        configuration = QuicConfiguration(
            is_client=False,
            alpn_protocols=H3_ALPN,
            idle_timeout=5,
            max_data=65536,
            max_stream_data=8192,
        )
        configuration.load_cert_chain(directory / "cert.pem", directory / "key.pem")
        _, listener = await loop.create_datagram_endpoint(
            lambda: RestrictedServer(
                configuration=configuration,
                create_protocol=lambda *a, **kw: HTTP3(*a, lab_config=config, **kw),
                retry=True,
                peers=config["peers"],
            ),
            local_addr=(config["bind_address"], config["port"]),
        )
    print(
        json.dumps({"ready": True, "port": config["port"], "certificate": pem}),
        flush=True,
    )
    try:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stopped.wait(), 55)
    finally:
        listener.close()
        if config["protocol"] == "tls":
            await listener.wait_closed()
        for task in list(tasks):
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    return {"node_id": config["node_id"], "stopped": True}


async def client(config: dict) -> dict:
    observations = []
    for payload in config["payloads"]:
        raw = bytes.fromhex(payload)
        sample = {
            "client": config["node_id"],
            "backend": config["target_node"],
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes_echoed": 0,
            "rtt_ms": 0,
            "status": "failed",
            "handshake_ms": None,
            "request_ms": None,
            "failure_reason": None,
            "timeout": False,
            "retry_packets": None,
            "session_resumed": False,
        }
        logger = SafeLogger() if config["protocol"] == "h3" else None
        data = json.dumps({"token": config["token"], "payload": payload}).encode()
        started = time.perf_counter()
        stage = "handshake"
        try:
            async with asyncio.timeout(4):
                if config["protocol"] == "tls":
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.minimum_version = context.maximum_version = (
                        ssl.TLSVersion.TLSv1_3
                    )
                    if not config.get("controlled_failure"):
                        context.load_verify_locations(cadata=config["certificate"])
                    reader, writer = await asyncio.open_connection(
                        config["host"],
                        config["port"],
                        ssl=context,
                        server_hostname=config["host"],
                        ssl_handshake_timeout=5,
                    )
                    try:
                        sample["handshake_ms"] = (time.perf_counter() - started) * 1000
                        stage = "request"
                        request_start = time.perf_counter()
                        writer.write(struct.pack("!I", len(data)) + data)
                        await writer.drain()
                        response = await read_frame(reader)
                        sample["request_ms"] = (
                            time.perf_counter() - request_start
                        ) * 1000
                        sample["tls_version"] = writer.get_extra_info(
                            "ssl_object"
                        ).version()
                    finally:
                        writer.close()
                        with contextlib.suppress(OSError, TimeoutError):
                            await asyncio.wait_for(writer.wait_closed(), 1)
                else:
                    configuration = QuicConfiguration(
                        is_client=True,
                        alpn_protocols=H3_ALPN,
                        idle_timeout=5,
                        quic_logger=logger,
                        server_name=config["host"],
                        cadata=None
                        if config.get("controlled_failure")
                        else config["certificate"].encode(),
                    )
                    async with connect(
                        config["host"],
                        config["port"],
                        configuration=configuration,
                        create_protocol=HTTP3,
                    ) as connection:
                        sample["handshake_ms"] = (time.perf_counter() - started) * 1000
                        stage = "request"
                        request_start = time.perf_counter()
                        response = await connection.request(data)
                        sample["request_ms"] = (
                            time.perf_counter() - request_start
                        ) * 1000
                        sample["alpn"] = "h3"
                decoded = json.loads(response)
                if (
                    decoded.get("payload") != payload
                    or decoded.get("backend") != config["target_node"]
                ):
                    raise ValueError("payload_mismatch")
                sample.update(status="succeeded", bytes_echoed=len(raw))
        except TimeoutError:
            sample.update(failure_reason=stage + "_timeout", timeout=True)
        except ssl.SSLCertVerificationError:
            sample["failure_reason"] = "certificate_verification_failed"
        except ConnectionError:
            sample["failure_reason"] = (
                "quic_or_tls_handshake_failed"
                if stage == "handshake"
                else "connection_closed"
            )
        except (OSError, ValueError, asyncio.IncompleteReadError):
            sample["failure_reason"] = stage + "_failed"
        sample["rtt_ms"] = (time.perf_counter() - started) * 1000
        if logger:
            sample["qlog"] = logger.export()
            sample["retry_packets"] = read_qlog(sample["qlog"])["retry_packets"]
        observations.append(sample)
        if sample["status"] != "succeeded":
            return {
                "status": "failed",
                "error": sample["failure_reason"],
                "observations": observations,
            }
    return {"status": "succeeded", "observations": observations}


def session(config: dict, role: str) -> dict:
    if role == "client":
        return asyncio.run(client(config))
    if role != "server":
        raise ValueError("secure_relay_not_supported")
    parent = Path(__file__).resolve().parents[4] / "artifacts" / "secure"
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="session-", dir=parent) as temporary:
        return asyncio.run(server(config, Path(temporary)))
