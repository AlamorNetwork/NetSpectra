# NetSpectra operator panel

A buildless Persian RTL interface with charcoal surfaces, soft green accents,
self-hosted Vazirmatn and Lucide icons. There is no third-party runtime request.

## Local start

From the repository root after `uv sync --locked`:

```sh
uv run pprl-panel --data-dir artifacts/panel init --credentials-file artifacts/panel-access.json
uv run pprl-panel --data-dir artifacts/panel serve --port 8765
```

Open http://127.0.0.1:8765 and read the generated private credentials file.
The initializer refuses to overwrite an existing account. Plaintext credentials
are never placed in tracked source or returned by an API. The store contains a
salted scrypt hash; the explicitly requested access file contains the initial
password and must be protected. Sessions expire after twelve hours or restart.

## Capabilities and boundaries

- Create immutable named TCP/UDP configurations with seed, repetitions and bounded
  timeout/retry controls. Copy a configuration to adjust it.
- Execute one job at a time, stop it cooperatively, inspect real artifacts,
  download JSON, and replay the recorded snapshot and execution policy.
- View history, real sample/byte counts, attempt outcomes, Git provenance and
  artifact integrity failures. Restarted jobs are marked interrupted, not resumed.
- All measurement traffic remains synthetic IPv4 loopback. The admin HTTP
  connection is separate; the UI cannot select an external probe destination.
- This is a single administrator panel, not a general shell, multi-user service,
  packet capture tool or implementation of W03 namespace experiments.

The same CLI schema validation, path checks, content hashes and execution bounds
apply. POST requests require the client header and a matching Origin when supplied.
Cookies are HttpOnly and SameSite Strict, and Secure on HTTPS. Public listening
requires TLS, with explicit allowed hosts. Proxy headers are disabled. Login has
a per-IP failure limit; no cross-origin API is enabled.

## Ubuntu IP deployment

Pull committed source first; never copy edited source onto the server:

```sh
git pull --ff-only
.tools/uv sync --locked
.tools/uv run --locked python scripts/deploy_panel.py --ip 54.36.113.36
systemctl status netspectra-panel --no-pager
```

The deployment script requires root and a clean checkout. It initializes only
missing credentials, generates a 90-day self-signed IP certificate, and installs
`netspectra-panel.service` on HTTPS port 443 (override with `--port`). It refuses to replace an unrelated
listener during first installation. It preserves existing configurations/results
on subsequent deployment. Runtime state, TLS key and initial access file are in
ignored `artifacts/panel/` (directory mode 0700). Source stays in Git.

Open **https://54.36.113.36**. A self-signed certificate causes a browser trust
warning until the certificate is explicitly trusted by the operator. Retrieve the
public `artifacts/panel/tls.crt` over the established SSH connection to verify it.
Use a trusted certificate before wider distribution. Existing certificates are
preserved; replace them before expiry and restart the service. Future nginx/CDN
deployment must explicitly configure trusted hosts, HTTPS and proxy handling.

The service uses `NoNewPrivileges`, a read-only filesystem except its state
directory, private temporary files and control-group process cleanup. It currently
runs as root because the existing lab checkout and Python runtime are under
`/root`; migrate both into a dedicated service account before wider use.

## Verification

`uv run --locked pytest tests/integration/test_panel.py` covers authentication,
rate limiting, origin/host rejection, local static assets, TCP/UDP execution,
immutable replay, cancellation, invalid configuration and restart recovery.
Browser acceptance additionally exercises the actual Persian interface.

Asset license files are adjacent to the font and icon assets.
