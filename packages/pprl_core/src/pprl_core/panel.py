"""Private operator panel for the existing synthetic experiment engine."""

import argparse
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

from pprl_core import __version__, cli

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
        self, identifier: str, execution: Execution | None = None, replay: bool = False
    ) -> dict:
        cli.inspect(self.root, identifier)  # validate ownership/path before enqueueing
        with self.lock:
            if self.active:
                raise HTTPException(409, "runner_busy")
            job = {
                "job_id": "job-" + uuid.uuid4().hex,
                "status": "running",
                "target": identifier,
                "kind": "replay" if replay else "run",
                "started_at": cli._now(),
                "run_id": None,
                "error": None,
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
        try:
            if replay:
                result, _ = cli.replay(self.root, target, _cancel_event=event)
            else:
                result, _ = cli.run(self.root, target, **policy, _cancel_event=event)
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
            "scope": "ipv4_loopback_only",
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
