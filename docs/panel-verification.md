# Operator panel acceptance — 2026-10-31

The requested early operator UI is implemented before W03. It is Persian RTL,
charcoal with soft green accents, and uses real filesystem-backed engine results.

## Verified

- Windows: 130 tests passed; Ruff and format checks passed; wheel and sdist built.
- Ubuntu 24.04: 130 tests passed before service deployment.
- Browser: sign-in, configuration creation, three-sample TCP run, result details,
  and replay completed; both runs returned 734 synthetic bytes. Screenshots are
  local ignored artifacts, not fabricated data.
- Remote HTTPS API: login, clean Git provenance, TCP run and replay, UDP run and
  replay, and logout verified from Windows against the actual server. Certificate
  verification stayed enabled using the public certificate retrieved over SSH.
- CI run 19 passed for implementation commit `841e01b`; subsequent commits have
  their own CI runs and should be checked on the PR.

The four remote acceptance run IDs were:

```text
run-ef21b8d8276a486791914124dad4bd0a
run-0c8d66b3d645412e9671abfc81d9895a
run-a6ee2f0f531f48d89fcfab5ad6a32157
run-8ef8c4e4e9cf4aafb3d01afd5b83c682
```

Source on the server was updated exclusively with `git pull --ff-only`. The
tracked deployment script generated runtime authentication/TLS files and installed
the systemd service. The service preserves existing state across redeployments.

## Access and known limits

HTTPS is on the standard TCP port 443 at the configured server IP. Port 8765 was
reachable inside the server but timed out from the operator computer; no SYN
arrived in the narrow server-side diagnostic capture. No firewall was disabled.
TCP 443 was unused before installation; existing unrelated UDP services and rules
were preserved. Persistent HTTPS connections made the external smoke reliable
after intermittent TLS resets with one new connection per request.

The IP certificate is self-signed, valid for 90 days and has the IP SAN. Initial
browser trust is an operator action. Credentials are in an ignored private access
file, never committed. Authentication sessions expire on restart. The service
currently runs from the existing root-owned checkout with systemd filesystem
restrictions; dedicated-account migration and trusted TLS are documented in the
panel guide. One Starlette TestClient deprecation warning is emitted for httpx;
it does not affect the 130 passing tests.

Only seeded synthetic loopback TCP/UDP is exposed. W03 namespaces and impairment,
general probes, packet capture and multi-user administration remain unimplemented.
