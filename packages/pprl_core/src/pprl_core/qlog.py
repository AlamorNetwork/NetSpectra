"""Bounded qlog 0.3 projection: no addresses, IDs, headers, tokens or secrets."""

import math
import time

from aioquic.quic.logger import QuicLogger, QuicLoggerTrace

PACKETS = {"initial", "handshake", "0RTT", "1RTT", "retry", "version_negotiation"}
METRICS = {
    "latest_rtt",
    "min_rtt",
    "smoothed_rtt",
    "rtt_variance",
    "congestion_window",
    "bytes_in_flight",
    "ssthresh",
    "pto_count",
}


def project(name: str, data: dict) -> dict | None:
    if name in {
        "transport:packet_sent",
        "transport:packet_received",
        "recovery:packet_lost",
    }:
        packet = data.get("header", {}).get("packet_type", data.get("type"))
        if packet not in PACKETS:
            return None
        result = {"header": {"packet_type": packet}}
        length = data.get("raw", {}).get("length")
        if type(length) is int and 0 <= length <= 65535:
            result["raw"] = {"length": length}
        return result
    if name == "recovery:metrics_updated":
        return {
            k: v
            for k, v in data.items()
            if k in METRICS
            and type(v) in {int, float}
            and math.isfinite(v)
            and 0 <= v <= 1e12
        }
    return None


class SafeTrace(QuicLoggerTrace):
    def __init__(self, *, is_client: bool, odcid: bytes):
        super().__init__(is_client=is_client, odcid=b"")
        self.started = time.perf_counter()
        self.limit_reached = False

    def log_event(self, *, category: str, event: str, data: dict) -> None:
        name = category + ":" + event
        clean = project(name, data)
        if clean is None:
            return
        if len(self._events) >= 2000:
            self.limit_reached = True
            return
        self._events.append(
            {
                "name": name,
                "time": (time.perf_counter() - self.started) * 1000,
                "data": clean,
            }
        )

    def to_dict(self) -> dict:
        return {
            "vantage_point": {"name": "netspectra", "type": "client"},
            "common_fields": {"time_format": "relative"},
            "events": list(self._events),
        }


class SafeLogger(QuicLogger):
    def start_trace(self, is_client: bool, odcid: bytes) -> SafeTrace:
        if self._traces:
            raise ValueError("one connection per qlog")
        trace = SafeTrace(is_client=is_client, odcid=odcid)
        self._traces.append(trace)
        return trace

    def export(self) -> dict:
        return self.to_dict() | {
            "projection": "netspectra-headers-v1",
            "limit_reached": any(t.limit_reached for t in self._traces),
        }


def read_qlog(document: dict) -> dict:
    """Version-aware, fail-closed reader used again at the controller boundary."""
    if document.get("qlog_version") != "0.3" or document.get("qlog_format") != "JSON":
        raise ValueError("unsupported_qlog_version")
    if set(document) != {
        "qlog_version",
        "qlog_format",
        "traces",
        "projection",
        "limit_reached",
    }:
        raise ValueError("invalid_qlog")
    if (
        document["projection"] != "netspectra-headers-v1"
        or type(document["limit_reached"]) is not bool
    ):
        raise ValueError("invalid_qlog")
    traces = document["traces"]
    if not isinstance(traces, list) or len(traces) != 1:
        raise ValueError("invalid_qlog")
    trace = traces[0]
    if (
        set(trace) != {"vantage_point", "common_fields", "events"}
        or trace["vantage_point"] != {"name": "netspectra", "type": "client"}
        or trace["common_fields"] != {"time_format": "relative"}
    ):
        raise ValueError("invalid_qlog")
    events = trace["events"]
    if not isinstance(events, list) or len(events) > 2000:
        raise ValueError("invalid_qlog")
    counts = {
        "packets_sent": 0,
        "packets_received": 0,
        "retry_packets": 0,
        "loss_events": 0,
    }
    previous = 0
    for event in events:
        if set(event) != {"name", "time", "data"}:
            raise ValueError("invalid_qlog")
        stamp = event["time"]
        if (
            type(stamp) not in {int, float}
            or not math.isfinite(stamp)
            or not previous <= stamp <= 60000
        ):
            raise ValueError("invalid_qlog")
        previous = stamp
        if (
            not isinstance(event["data"], dict)
            or project(event["name"], event["data"]) is None
            or project(event["name"], event["data"]) != event["data"]
        ):
            raise ValueError("invalid_qlog")
        if event["name"] == "transport:packet_sent":
            counts["packets_sent"] += 1
        if event["name"] == "transport:packet_received":
            counts["packets_received"] += 1
            if event["data"].get("header", {}).get("packet_type") == "retry":
                counts["retry_packets"] += 1
        if event["name"] == "recovery:packet_lost":
            counts["loss_events"] += 1
    return counts | {
        "event_count": len(events),
        "limit_reached": document["limit_reached"],
    }
