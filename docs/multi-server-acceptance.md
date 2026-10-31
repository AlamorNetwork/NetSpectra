# Multi-server acceptance — 2026-10-31

Controller: `54.36.113.36`. Iran worker: `87.107.146.217`, SSH port 9011.
All measurements below are actual inter-server runs initiated through the panel
API on the controller, with three seeded samples and 734 echoed bytes per run.

| Path | Protocol | Result | Run ID |
| --- | --- | --- | --- |
| Iran → outside | TCP | succeeded | `net-1181fa5573e54d4f9379a3e027d43a88` |
| Iran → outside | UDP | succeeded | `net-36ce8361d8564bcd9eb007e2975e67e6` |
| Outside → Iran | TCP | succeeded | `net-25feba1347154c448c3be52aeaefbfe1` |
| Outside → Iran | UDP | succeeded | `net-0b708f38eb8d4343aa1c1faef95c20eb` |
| Iran → outside relay → Iran | TCP | succeeded | `net-ac198999c71a42e6bed1d22322bb6910` |
| Iran → outside relay → Iran | UDP | succeeded | `net-5baa214259cf42daacc0a518ee0c27f8` |

The relay reports identify `eu-1` as the intermediary and `iran-1` as the actual
backend. Their observed application round-trip times were 305.70/323.17/345.22 ms
for TCP and 163.31/153.23/149.00 ms for UDP. These are small observed samples,
not a throughput benchmark, population estimate or pure network-latency metric.
Earlier SSH-authorization failures remain in history; they were not deleted or
presented as successful measurements.

## Isolation and installation

- Iran installation is confined to the newly created `/opt/netspectra-ir-v1`.
  Outside worker is in newly created `/opt/netspectra-eu-v1`.
- Worker source was cloned/fetched from GitHub. Existing Phoenix folders,
  firewall/routing rules, occupied ports and unrelated services were not edited
  or stopped. Required git/python3 already existed, so no system package install
  or global Python change was needed.
- The operator explicitly approved adding one dedicated controller public-key
  line to Iran's `/root/.ssh/authorized_keys`. It is restricted to source IP
  `54.36.113.36`, with SSH forwarding and PTY disabled. Original bytes were backed
  up inside the new worker folder and preserved as an unchanged prefix. Existing
  private identities were not copied to the controller.
- The controller successfully checked Iran over SSH and installed its outside
  worker through SSH itself. Worker updates use only a checked clean Git checkout
  and fast-forward; unrelated directories are not deployment targets.
- Test port 28080 is temporary, with normal exclusive bind. Agents close on
  control-channel EOF or bounded timeout, and the controller reaps child SSH
  processes. Port-collision behavior is exercised by actual socket tests.

## Verification and reproducibility

154 tests pass on Windows and Ubuntu 24.04, including real local child-process
TCP/UDP workers, direct orchestration, shared client/backend roles through a
separate relay, multi-backend round-robin, occupied-port preservation, topology
validation, authentication and artifact-integrity checks. Ruff and builds pass.
One existing Starlette/httpx TestClient deprecation warning remains.

Open **سرورها و مسیرها**, select an existing topology and press **اجرای مسیر**.
Inspect **جزئیات** for per-sample source, intermediary, backend, bytes and timing;
download JSON for the snapshots, hashes and controller/worker Git provenance.
Network artifact schema version is 1.0.0; local loopback contracts remain unchanged.

The direct acceptance runs used implementation `826de28`; the relay runs used
`c6fb172` on controller and workers. Later UI/evidence commits do not rewrite those
immutable records. Final deployment source synchronization is checked separately.

For visual acceptance, authentic checksummed server reports were fetched into
the local preview store and inspected in the browser. Screenshots show those
actual reports, not a live remote browser session or fabricated chart data.
