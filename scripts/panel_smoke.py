"""Verify a deployed panel using its explicitly trusted certificate and account."""

import argparse
import http.cookiejar
import json
import ssl
import time
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--certificate", required=True, type=Path)
    args = parser.parse_args()
    if not args.url.startswith("https://"):
        parser.error("HTTPS required")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=str(args.certificate))
        ),
    )

    def request(path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        message = urllib.request.Request(
            args.url.rstrip("/") + path,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-NetSpectra-Client": "panel",
                "Origin": args.url.rstrip("/"),
            },
        )
        with opener.open(message, timeout=15) as response:
            return json.load(response)

    def wait(job: dict) -> dict:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            state = request("/api/state")
            current = next(j for j in state["jobs"] if j["job_id"] == job["job_id"])
            if current["status"] not in {"running", "cancelling"}:
                if current["status"] != "succeeded":
                    raise RuntimeError(f"job failed: {current['error']}")
                return request("/api/runs/" + current["run_id"])
            time.sleep(0.2)
        raise TimeoutError("panel job did not complete")

    request("/api/login", json.loads(args.credentials.read_text(encoding="utf-8-sig")))
    health = request("/api/health")
    if health["source"]["dirty"] is not False:
        raise RuntimeError("deployment source is dirty or unavailable")
    runs = []
    for protocol in ("tcp", "udp"):
        config = request(
            "/api/experiments",
            {"name": "بررسی پایهٔ " + protocol.upper(), "protocol": protocol},
        )
        result = wait(request(f"/api/experiments/{config['experiment_id']}/run", {}))
        repeated = wait(request(f"/api/runs/{result['record']['run_id']}/replay", {}))
        assert result["record"]["sample_size"] == 3
        assert (
            result["summary"]["workload_sha256"]
            == repeated["summary"]["workload_sha256"]
        )
        runs.extend([result["record"]["run_id"], repeated["record"]["run_id"]])
    request("/api/logout", {})
    assert request("/api/session")["authenticated"] is False
    print(json.dumps({"health": health, "verified_runs": runs}, indent=2))


if __name__ == "__main__":
    main()
