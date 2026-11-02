# W04 acceptance and unresolved path behavior — 2026-10-31

Measured implementation: `6cda5e65782e52ed80edebc01bc22eabb41fecf4`, clean and
identical on controller and both workers. Subsequent UI/documentation changes do
not change the measured protocol implementation. Python 3.12, aioquic 1.7.0;
workers use native Python 3.12.3 in their dedicated virtual environments.

## Actual two-server observations

Each successful run used port 28080, seed 42, three fresh connections and 734
application bytes total. Data used the selected network path, not SSH tunneling.

| Case | Run ID | Actual result | Mean establishment / request ms |
| --- | --- | --- | --- |
| HTTP3 Iran to outside | net-e5b54003a27143ecacea34114b5096a8 | handshake_timeout | unavailable |
| HTTP3 outside to Iran | net-5d6017a11f1e4589803c46b779ec6378 | handshake_timeout | unavailable |
| TLS outside to Iran 1 | net-0463b65847e14086986e7efc3bb673d4 | succeeded, 3 samples | 177.99 / 209.55 |
| TLS outside to Iran 2 | net-d6fcd939dfbe460392e5de99a906deab | succeeded, 3 samples | 172.42 / 202.96 |
| TLS outside to Iran 3 | net-381142cdb4564cbca43a39a29555adaf | succeeded, 3 samples | 166.10 / 197.56 |
| TLS outside to Iran, trust anchor deliberately omitted | net-756294e17224420e82f6dea13494f232 | certificate_verification_failed, expected_certificate_rejection=true | unavailable |
| TLS Iran to outside | net-9306dbd140e940cd9e8b4c7c114c531d | quic_or_tls_handshake_failed | unavailable |

Failed runs preserve the failed sample with zero echoed bytes and null establishment
time rather than inventing a successful duration. Certificate failure is classified
separately; a generic handshake failure/timeout is not a certificate-rejection proof.

Fourteen PCAP/CSV capture pairs and two projected client qlogs were produced for
these seven runs. Each authenticated download matched the bound artifact SHA256;
qlogs passed the version/projection reader and contained no original addresses,
PEM material, token/payload fields or ODCID. Zero-packet destination captures are
valid evidence of this failure, not successful QUIC measurements.

In **each** HTTP3 direction, source capture recorded six outbound UDP packets,
7368 IPv4 bytes; destination capture recorded zero matching packets. Client qlog
recorded six sends, zero receives, zero Retry packets and four loss events. These
events describe this client's recovery decisions, not a measured network loss rate.
The client deadline fired and the run remained failed.

## Controls and uncertainty

- On the same port, ordinary UDP Iran-to-outside succeeded:
  `net-cdcd6f19e2684fcbb6d38e517693bed9` (3 samples, 734 echoed bytes).
- Ordinary TCP succeeded on that path:
  `net-32660804e6aa4e05a697e859e95ad25a` (3 samples, 734 echoed bytes).
- Additional bounded UDP controls sent JSON requests of exactly 512, 1100, 1200
  and 1400 bytes, with 64-byte echo payload, in **both** directions. All eight
  succeeded on port 28080. This does not support a simple universal 1200-byte UDP
  size ceiling as the explanation for QUIC failure.
- Earlier HTTP3 on port 28180 also timed out. Earlier diagnostic runs remain in
  history; they were not replaced by the final acceptance table.
- Hypothesis: packet classification or path policy may distinguish QUIC and
  outbound TLS. This is **not proven**; these endpoint observations do not identify
  the device, rule, mechanism, or cause. No filtering or firewall settings changed.
- Unknown: exact disappearance point, successful cross-server QUIC behavior,
  one-way latency, network loss rate and performance under load.

## Reproduction, validation and boundaries

Ubuntu root full suite: **217 passed** on 6cda5e6. Windows full suite: 215 passed,
2 Linux-only skips on c326d9e; after the endpoint capture/certificate classification
adjustment, targeted integration/parser suite: 42 passed, 2 skips. Hosted CI on
6cda5e6 passed on Ubuntu and Windows. One pre-existing Starlette/httpx deprecation
warning remains. Ruff, formatting, JavaScript syntax and package builds passed.

A fresh GitHub clone into a new controller artifacts directory, with a new venv
and locked dependency sync, passed all 17 secure/qlog checks on c326d9e. Those
checks include real local TLS/HTTP3 success, actual certificate rejection for both,
occupied-port preservation, cleanup, silent-endpoint timeout and download tampering.
Local HTTP3 success is explicitly not cross-server QUIC success.

After acceptance, worker secure/capture temporary directories were empty and
ports 28080/28180 had no listeners. Worker dependency installs were confined to
the existing dedicated NetSpectra directories. No Phoenix folders, services,
occupied ports, authorized_keys or firewall rules changed in W04.

Browser QA used a local panel preview with authentic copied server reports and
redacted artifacts. It inspected per-sample durations/failures, the four analysis
categories, capture counters and an actual qlog download. Runtime data stay ignored.

The implementation is ready for independent review; **W04 and the monthly gate
remain open** pending actual cross-server QUIC success and independent reproduction.
See [operator guide and limitations](../../docs/secure-baseline.md).
