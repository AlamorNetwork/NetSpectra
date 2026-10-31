# W03 instrumented acceptance — 2026-10-31

Measured implementation SHA: `7a83647889b7b14066bbf8a5ad603b8e0821855a`.
The controller and both workers used this clean Git revision. Later evidence-only
commits do not change the measured implementation.

Each case used three synthetic echo samples (734 application bytes total), port
28080 and seed 42. Data travelled directly between selected servers; SSH carried
control and redacted results. The relay cases used Iran as client/backend and the
outside worker as relay. Eight captures produced eight PCAP and eight CSV files.

| Case | Run ID | Capture vantage | Packets | IPv4 bytes |
| --- | --- | --- | ---: | ---: |
| Iran to outside TCP | net-a0cbd270b9c541a2b18c30dce72ed435 | outside | 30 | 4883 |
| Iran to outside UDP | net-71df56a069da44c7bb8b631526b124b1 | outside | 6 | 3419 |
| Outside to Iran TCP | net-ed97129924be4e3a9b7ecc864491c39d | Iran | 30 | 4889 |
| Outside to Iran UDP | net-ae7af3b6ec774b1aacb35c15869d3ae1 | Iran | 6 | 3425 |
| Iran through outside relay TCP | net-56e1e006e06742d6b16e9f9469211089 | Iran; outside (each) | 60 | 9778 |
| Iran through outside relay UDP | net-a2b7d4166bf2422fbd0fb5bea34b8096 | Iran; outside (each) | 12 | 6850 |

All six runs succeeded. Each capture reported zero kernel drops, zero excluded
records and no packet-cap limit. Counts from different vantage points may include
the same packets and must not be added as unique network traffic. Zero capture
drops does not establish zero network loss. IPv4 bytes differ from application bytes.

Authenticated PCAP/CSV downloads matched their recorded hashes. Export checks
found no original IPv4 address bytes, per-run tokens or synthetic payload marker.
The controller reparses sanitized PCAP and regenerates flow hashes before accepting
worker results. Unauthorized downloads, unknown nodes and modified artifacts are
covered by API integration tests.

After acceptance, worker capture temporary directories were empty and TCP/UDP
port 28080 was free. Existing Phoenix folders, occupied ports, firewall rules and
services were preserved. Only the previously approved restricted controller key
line was appended to Iran authorized_keys; prior bytes were backed up and retained.

Compatibility fixes verified during acceptance: canonical LF CSV across Windows
and Linux; Linux TCP TIME_WAIT reuse without sharing an active listener; omission
of tcpdump's optional `-Z root`, which caused a native crash on the Iran host.
Capture processes disable core dumps. Earlier failed run records remain intact.

Validation: Windows 198 passed / 2 Linux-only skips; Ubuntu 200 passed before the
last invocation adjustment, followed by 2 capture/API integration passes and the
six successful instrumented cases above after adjustment. Ruff, formatting,
JavaScript syntax and package builds are checked separately. CI for the measured
implementation passed. Browser QA used a local panel preview of authentic copied
reports and capture artifacts; it was not a remote browser session.

Runtime captures and operational acceptance JSON stay private in ignored artifacts.
Public deterministic fixtures are synthetic. See [capture boundaries and cleanup
limitations](../../docs/capture.md), including the abrupt hard-kill caveat.
