"""Private operator panel for the existing synthetic experiment engine."""

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import platform
import secrets
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pprl_core import __version__, cli, cluster_runner
from pprl_core.cluster import Inventory, Node, Topology
from pprl_core.cluster_ssh import SSH

COOKIE = "netspectra_session"


class Execution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout: float = Field(default=20, gt=0, le=30, allow_inf_nan=False, strict=True)
    retries: int = Field(default=1, ge=0, le=2, strict=True)
    attempt_timeout: float = Field(
        default=5, gt=0, le=30, allow_inf_nan=False, strict=True
    )
    retry_delay: float = Field(
        default=0.05, ge=0, le=1, allow_inf_nan=False, strict=True
    )


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64, pattern=r"\S")
    protocol: Literal["tcp", "udp"] = "tcp"
    run_seed: int = Field(default=42, ge=0, le=4294967295, strict=True)
    repetitions: int = Field(default=3, ge=1, le=10, strict=True)
    execution: Execution = Field(default_factory=Execution)


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class NetworkExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture: bool | None = Field(default=None, strict=True)


def _password_hash(password: str, salt: str) -> str:
    return hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32
    ).hex()


def initialize(root: Path, credentials_file: Path) -> None:
    """Write only the password hash to the store; plaintext goes to an explicit file."""
    root.mkdir(parents=True, exist_ok=True)
    auth = cli._path(root, "panel-auth.json")
    if auth.exists() or credentials_file.exists():
        raise cli.CLIError("panel_already_initialized")
    password = secrets.token_urlsafe(24)
    salt = secrets.token_hex(16)
    with credentials_file.open("x", encoding="utf-8") as destination:
        os.chmod(credentials_file, 0o600)
        json.dump({"username": "admin", "password": password}, destination)
    cli._atomic_write(auth, {"salt": salt, "hash": _password_hash(password, salt)})


class Controller:
    def __init__(self, root: Path):
        self.root = root
        self.inventory = Inventory(root)
        self.ssh = SSH(root)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="panel-run"
        )
        self.jobs: dict[str, dict] = {}
        self.cancel_event: threading.Event | None = None
        self.active: str | None = None
        directory = cli._path(root, "panel-jobs")
        directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(directory.glob("job-*.json"))[-100:]:
            if path.is_symlink():
                continue
            try:
                job = cli._read(path)
                if job.get("job_id") + ".json" != path.name:
                    continue
                if job.get("status") in {"running", "cancelling"}:
                    job.update(status="interrupted", error="server_restarted")
                    cli._atomic_write(path, job)
                self.jobs[job["job_id"]] = job
            except (OSError, cli.CLIError, TypeError):
                continue

    def close(self) -> None:
        with self.lock:
            if self.cancel_event:
                self.cancel_event.set()
        self.executor.shutdown(wait=True, cancel_futures=True)

    def _job_file(self, identifier: str) -> Path:
        return cli._path(self.root, "panel-jobs", identifier + ".json")

    def configuration(self, record: dict) -> dict:
        path = cli._path(self.root, "panel-configs", record["experiment_id"] + ".json")
        extra = cli._read(path) if path.exists() else {}
        return record | {
            "name": extra.get("name", record["experiment_id"]),
            "execution": extra.get("execution", Execution().model_dump()),
        }

    def create(self, data: Configuration) -> dict:
        record = {
            "schema_version": "0.1.0",
            "experiment_id": "exp-" + uuid.uuid4().hex[:16],
            "scenario": "seeded_echo",
            "scenario_version": 1,
            "run_seed": data.run_seed,
            "protocol": data.protocol,
            "repetitions": data.repetitions,
            "lab_mode": "isolated",
            "consent_scope": "synthetic_only",
            "network_profile": {
                "latency_ms": 0,
                "packet_loss_pct": 0,
                "bandwidth_mbps": 100,
            },
            "artifacts": {"retain_raw_pcap": False, "retain_qlog": False},
        }
        with self.lock:
            cli.register(self.root, record)
            path = cli._path(
                self.root, "panel-configs", record["experiment_id"] + ".json"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            cli._atomic_write(
                path,
                {"name": data.name.strip(), "execution": data.execution.model_dump()},
            )
        return self.configuration(record)

    def start(
        self,
        identifier: str,
        execution: Execution | None = None,
        replay: bool = False,
        kind: str | None = None,
        capture_override: bool | None = None,
    ) -> dict:
        if kind == "network":
            self.inventory.plan(self.inventory.topology(identifier))
        elif kind in {"bootstrap", "preflight", "dependencies"}:
            self.inventory.node(identifier)
        elif kind is None:
            cli.inspect(self.root, identifier)
        else:
            raise cli.CLIError("invalid_job_kind")
        with self.lock:
            if self.active:
                raise HTTPException(409, "runner_busy")
            job = {
                "job_id": "job-" + uuid.uuid4().hex,
                "status": "running",
                "target": identifier,
                "kind": kind or ("replay" if replay else "run"),
                "started_at": cli._now(),
                "run_id": None,
                "error": None,
                "capture_override": capture_override,
            }
            event = threading.Event()
            cli._atomic_write(self._job_file(job["job_id"]), job)
            self.active, self.cancel_event = job["job_id"], event
            self.jobs[job["job_id"]] = job
            self.executor.submit(
                self._execute,
                job["job_id"],
                event,
                (execution or Execution()).model_dump(),
                replay,
            )
            return dict(job)

    def _execute(
        self, identifier: str, event: threading.Event, policy: dict, replay: bool
    ) -> None:
        with self.lock:
            target = self.jobs[identifier]["target"]
            kind = self.jobs[identifier]["kind"]
        try:
            if kind in {"bootstrap", "preflight", "dependencies"}:
                node = self.inventory.node(target)
                if kind == "bootstrap":
                    source = cli._source_metadata()
                    if source["dirty"]:
                        raise cli.CLIError("clean_source_required")
                    result = asyncio.run(self.ssh.bootstrap(node, source["git_sha"]))
                elif kind == "dependencies":
                    result = asyncio.run(self.ssh.install_dependencies(node))
                else:
                    result = asyncio.run(self.ssh.preflight(node))
                outcome = {"status": "succeeded", "error": None, "result": result}
            elif kind == "network":
                result = cluster_runner.run(
                    self.root,
                    self.inventory,
                    self.ssh,
                    target,
                    event,
                    capture_override=self.jobs[identifier].get("capture_override"),
                )
                outcome = {
                    "status": result["status"],
                    "run_id": result["run_id"],
                    "error": result["failure_reason"],
                }
            elif replay:
                result, _ = cli.replay(self.root, target, _cancel_event=event)
            else:
                result, _ = cli.run(self.root, target, **policy, _cancel_event=event)
            if kind not in {"bootstrap", "preflight", "dependencies", "network"}:
                outcome = {
                    "status": result["status"],
                    "run_id": result["run_id"],
                    "error": result["failure_reason"],
                }
        except cli.CLIError as error:
            outcome = {"status": "failed", "error": str(error)}
        except Exception:
            outcome = {"status": "failed", "error": "internal_error"}
        with self.lock:
            job = self.jobs[identifier]
            job.update(outcome, finished_at=cli._now())
            try:
                cli._atomic_write(self._job_file(identifier), job)
            finally:
                self.active = self.cancel_event = None

    def cancel(self, identifier: str) -> dict:
        with self.lock:
            if identifier != self.active or self.cancel_event is None:
                raise HTTPException(409, "job_not_running")
            self.cancel_event.set()
            self.jobs[identifier]["status"] = "cancelling"
            cli._atomic_write(self._job_file(identifier), self.jobs[identifier])
            return dict(self.jobs[identifier])

    def state(self) -> dict:
        experiments = [
            self.configuration(item)
            for item in cli.list_experiments(self.root)["experiments"]
        ]
        runs = []
        directory = cli._path(self.root, "runs")
        if directory.exists():
            for path in directory.iterdir():
                if not path.name.startswith("run-"):
                    continue
                if not cli._path(directory, path.name, "run.json").exists():
                    continue
                try:
                    runs.append(cli.inspect(self.root, path.name))
                except (cli.CLIError, OSError):
                    runs.append(
                        {
                            "run_id": path.name,
                            "status": "integrity_error",
                            "started_at": "",
                            "experiment_id": "unknown",
                        }
                    )
        runs.sort(key=lambda item: item["started_at"], reverse=True)
        with self.lock:
            jobs = sorted(
                (dict(job) for job in self.jobs.values()),
                key=lambda job: job["started_at"],
                reverse=True,
            )[:20]
            active = dict(self.jobs[self.active]) if self.active else None
        return {
            "cluster": self.inventory.read(),
            "network_runs": self.network_runs(),
            "experiments": experiments[:200],
            "runs": runs[:50],
            "jobs": jobs,
            "active_job": active,
            "stats": {
                "experiments": len(experiments),
                "runs": len(runs),
                "succeeded": sum(r["status"] == "succeeded" for r in runs),
            },
        }

    def network_runs(self) -> list[dict]:
        directory = cli._path(self.root, "network-runs")
        if not directory.exists():
            return []
        records = []
        for path in directory.glob("net-*.json"):
            try:
                records.append(self.network_record(path.stem))
            except (cli.CLIError, OSError, KeyError, ValueError):
                records.append(
                    {
                        "run_id": path.stem,
                        "status": "integrity_error",
                        "started_at": "",
                        "topology": {"name": "گزارش نیازمند بررسی"},
                        "observations": [],
                        "failure_reason": "artifact_integrity_failed",
                    }
                )
        return sorted(records, key=lambda record: record["started_at"], reverse=True)[
            :50
        ]

    def network_record(self, identifier: str) -> dict:
        import re

        if not re.fullmatch(r"net-[0-9a-f]{32}", identifier):
            raise cli.CLIError("invalid_network_run_id")
        path = cli._path(self.root, "network-runs", identifier + ".json")
        expected = cli._read(path.with_suffix(".sha256"))["sha256"]
        if not hmac.compare_digest(
            hashlib.sha256(path.read_bytes()).hexdigest(), expected
        ):
            raise cli.CLIError("artifact_integrity_failed")
        return cli._read(path)


def _assets() -> Path:
    packaged = resources.files("pprl_core").joinpath("web_assets")
    if packaged.is_dir():
        return Path(str(packaged))
    return Path(__file__).resolve().parents[4] / "clients/web/assets"


def create_app(root: Path, allowed_hosts: list[str] | None = None) -> FastAPI:
    root = root.resolve()
    auth_path = cli._path(root, "panel-auth.json")
    auth = cli._read(auth_path)
    sessions: dict[str, float] = {}
    failures: dict[str, list[float]] = {}
    auth_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.controller = Controller(root)
        yield
        app.state.controller.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["127.0.0.1", "localhost"]
    )

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.method == "POST":
            length = request.headers.get("content-length", "")
            if not length.isdigit() or int(length) > 16384:
                return JSONResponse({"error": "invalid_request_size"}, status_code=413)
            if request.headers.get("x-netspectra-client") != "panel":
                return JSONResponse(
                    {"error": "invalid_request_origin"}, status_code=403
                )
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse(
                    {"error": "invalid_request_origin"}, status_code=403
                )
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; font-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                "form-action 'self'",
            }
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse({"error": "invalid_input"}, status_code=422)

    @app.exception_handler(cli.CLIError)
    async def cli_error(request: Request, error: cli.CLIError):
        return JSONResponse({"error": str(error)}, status_code=400)

    @app.exception_handler(OSError)
    async def io_error(request: Request, error: OSError):
        return JSONResponse({"error": "storage_or_io_error"}, status_code=400)

    def require_session(request: Request) -> None:
        token = request.cookies.get(COOKIE, "")
        digest = hashlib.sha256(token.encode()).hexdigest()
        with auth_lock:
            if sessions.get(digest, 0) < time.time():
                sessions.pop(digest, None)
                raise HTTPException(401, "authentication_required")

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        address = request.client.host if request.client else "unknown"
        now = time.time()
        with auth_lock:
            attempts = [t for t in failures.get(address, []) if now - t < 300]
            if len(attempts) >= 5:
                raise HTTPException(429, "login_rate_limited")
            if len(failures) >= 512:
                failures.clear()
            failures[address] = attempts
        expected = _password_hash(body.password, auth["salt"])
        if not (
            hmac.compare_digest(expected, auth["hash"]) and body.username == "admin"
        ):
            with auth_lock:
                failures.setdefault(address, []).append(now)
            raise HTTPException(401, "invalid_credentials")
        token = secrets.token_urlsafe(32)
        with auth_lock:
            expired = [key for key, expiry in sessions.items() if expiry < now]
            for key in expired:
                del sessions[key]
            if len(sessions) >= 256:
                sessions.pop(next(iter(sessions)))
            sessions[hashlib.sha256(token.encode()).hexdigest()] = now + 12 * 3600
            failures.pop(address, None)
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=12 * 3600,
        )
        return {"authenticated": True}

    @app.get("/api/session")
    def session(request: Request):
        try:
            require_session(request)
            return {"authenticated": True}
        except HTTPException:
            return {"authenticated": False}

    api = APIRouter(prefix="/api", dependencies=[Depends(require_session)])

    @api.post("/logout")
    def logout(request: Request, response: Response):
        digest = hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()
        with auth_lock:
            sessions.pop(digest, None)
        response.delete_cookie(COOKIE)
        return {"authenticated": False}

    @api.get("/state")
    def state(request: Request):
        return request.app.state.controller.state()

    @api.get("/health")
    def health():
        try:
            source = cli._source_metadata()
        except cli.CLIError:
            source = {"git_sha": None, "dirty": None}
        return {
            "version": __version__,
            "platform": platform.system(),
            "source": source,
            "scope": "loopback_and_selected_owned_nodes",
        }

    @api.post("/experiments", status_code=201)
    def create(body: Configuration, request: Request):
        return request.app.state.controller.create(body)

    @api.post("/experiments/{identifier}/run", status_code=202)
    def run(identifier: str, body: Execution, request: Request):
        return request.app.state.controller.start(identifier, body)

    @api.get("/runs/{identifier}")
    def run_details(identifier: str):
        record = cli.inspect(root, identifier)
        if "run_id" not in record:
            raise HTTPException(400, "run_required")
        directory = cli._path(root, "runs", identifier)
        return {
            "record": record,
            "summary": cli._read(directory / "summary.json"),
            "experiment": cli._read(directory / "experiment.json"),
        }

    @api.post("/runs/{identifier}/replay", status_code=202)
    def replay(identifier: str, request: Request):
        if not identifier.startswith("run-"):
            raise HTTPException(400, "run_required")
        return request.app.state.controller.start(identifier, replay=True)

    @api.post("/jobs/{identifier}/cancel")
    def cancel(identifier: str, request: Request):
        return request.app.state.controller.cancel(identifier)

    @api.post("/cluster/nodes", status_code=201)
    def add_node(body: Node, request: Request):
        return request.app.state.controller.inventory.add_node(body)

    @api.get("/cluster/key")
    def controller_key(request: Request):
        return {"public_key": request.app.state.controller.ssh.public_key()}

    @api.post("/cluster/nodes/{identifier}/update")
    def update_node(identifier: str, body: Node, request: Request):
        controller = request.app.state.controller
        with controller.lock:
            if controller.active:
                raise HTTPException(409, "runner_busy")
            return controller.inventory.update_node(identifier, body)

    @api.post("/cluster/key", status_code=201)
    def create_controller_key(request: Request):
        controller = request.app.state.controller
        with controller.lock:
            return {"public_key": controller.ssh.public_key(create=True)}

    @api.post("/cluster/nodes/{identifier}/scan")
    async def scan_host(identifier: str, request: Request):
        controller = request.app.state.controller
        return {
            "candidates": await controller.ssh.scan(
                controller.inventory.node(identifier)
            )
        }

    class HostKey(BaseModel):
        model_config = ConfigDict(extra="forbid")
        host_key: str = Field(
            max_length=200, pattern=r"^ssh-ed25519 [A-Za-z0-9+/]{40,100}={0,2}$"
        )

    @api.post("/cluster/nodes/{identifier}/pin")
    def pin_host(identifier: str, body: HostKey, request: Request):
        return request.app.state.controller.inventory.pin(identifier, body.host_key)

    @api.post("/cluster/nodes/{identifier}/bootstrap", status_code=202)
    def bootstrap_node(identifier: str, request: Request):
        return request.app.state.controller.start(identifier, kind="bootstrap")

    @api.post("/cluster/nodes/{identifier}/preflight", status_code=202)
    def check_node(identifier: str, request: Request):
        return request.app.state.controller.start(identifier, kind="preflight")

    @api.post("/cluster/topologies", status_code=201)
    def add_topology(body: Topology, request: Request):
        return request.app.state.controller.inventory.add_topology(body)

    @api.post("/cluster/plan")
    def plan_topology(body: Topology, request: Request):
        return request.app.state.controller.inventory.plan(body)

    @api.post("/cluster/topologies/{identifier}/run", status_code=202)
    def run_topology(identifier: str, body: NetworkExecution, request: Request):
        return request.app.state.controller.start(
            identifier, kind="network", capture_override=body.capture
        )

    @api.post("/cluster/nodes/{identifier}/dependencies", status_code=202)
    def install_dependencies(identifier: str, request: Request):
        return request.app.state.controller.start(identifier, kind="dependencies")

    @api.get("/cluster/runs/{identifier}/qlog/{trace_id}")
    def qlog_file(identifier: str, trace_id: str, request: Request):
        record = request.app.state.controller.network_record(identifier)
        artifact = next(
            (q for q in record.get("qlogs", []) if q["trace_id"] == trace_id), None
        )
        if artifact is None:
            raise HTTPException(404, "qlog_not_found")
        path = cli._path(root, "network-qlogs", identifier, trace_id + ".qlog")
        if not hmac.compare_digest(
            hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"]
        ):
            raise cli.CLIError("qlog_integrity_failed")
        return FileResponse(
            path,
            media_type="application/json",
            filename=identifier + "-" + trace_id + ".qlog",
        )

    @api.get("/cluster/runs/{identifier}")
    def network_details(identifier: str, request: Request):
        return request.app.state.controller.network_record(identifier)

    @api.get("/cluster/runs/{identifier}/capture/{node_id}/{kind}")
    def capture_file(identifier: str, node_id: str, kind: str, request: Request):
        record = request.app.state.controller.network_record(identifier)
        if kind not in {"pcap", "csv"}:
            raise HTTPException(404, "capture_not_found")
        capture = next(
            (
                item
                for item in record.get("captures", [])
                if item.get("node_id") == node_id and not item.get("error")
            ),
            None,
        )
        if capture is None:
            raise HTTPException(404, "capture_not_found")
        path = cli._path(root, "network-captures", identifier, node_id + "." + kind)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not hmac.compare_digest(digest, capture[kind + "_sha256"]):
            raise cli.CLIError("capture_integrity_failed")
        media = "application/vnd.tcpdump.pcap" if kind == "pcap" else "text/csv"
        return FileResponse(
            path, media_type=media, filename=identifier + "-" + node_id + "." + kind
        )

    app.include_router(api)
    assets = _assets()
    app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def index():
        return FileResponse(assets / "index.html")

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("artifacts/panel"))
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--credentials-file", type=Path, required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--certfile", type=Path)
    serve.add_argument("--keyfile", type=Path)
    serve.add_argument("--allowed-host", action="append", default=[])
    args = parser.parse_args()
    root = args.data_dir.resolve()
    if args.command == "init":
        initialize(root, args.credentials_file.resolve())
        print(json.dumps({"credentials_file": str(args.credentials_file.resolve())}))
        return 0
    if args.host not in {"127.0.0.1", "localhost"} and not (
        args.certfile and args.keyfile
    ):
        parser.error("public access requires --certfile and --keyfile")
    app = create_app(root, ["127.0.0.1", "localhost", *args.allowed_host])
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        proxy_headers=False,
        ssl_certfile=str(args.certfile) if args.certfile else None,
        ssl_keyfile=str(args.keyfile) if args.keyfile else None,
        access_log=False,
        limit_concurrency=20,
        timeout_keep_alive=5,
    )
    return 0
