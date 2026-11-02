# Scoped capture and instrumentation (W03)

In **سرورها و مسیرها**, choose **اجرا + PCAP**. The normal run button retains
the topology's existing capture setting. The run snapshot records the effective
choice; existing historical runs are unchanged.

The controller first starts the selected backends/relay with exclusive port
binding, then starts capture before clients send data. Capture runs at backend
and relay vantage points. Its kernel BPF filter permits only IPv4, the selected
TCP/UDP port and exact selected address pairs. No other application is stopped
or reconfigured. There is no unfiltered capture option in the panel.

Workers need their existing `tcpdump` and GNU `timeout` binaries and permission
to capture. No package is installed automatically and no global permissions are
changed. The swappable `CaptureAdapter` contract provides start, stop and close;
the current adapter uses non-promiscuous `any`, packet-buffered output and
immediate mode. See the [upstream tcpdump manual](https://github.com/the-tcpdump-group/tcpdump/blob/master/tcpdump.1.in).

## Bounds and shutdown

Each capture is limited to 2,000 packets, 256-byte snapshots and a 55-second
control wait, with a separate 60-second process watchdog. The watchdog terminates
even if its Python parent is lost. Each adapter has its own process group;
cleanup signals only processes it created. EOF, cancellation, errors and normal
completion stop capture, collect the final report and remove the private raw
temporary directory. A hard OS kill can leave a bounded private temporary file
inside the dedicated worker's ignored `artifacts/capture/`; normal Python cleanup
cannot be guaranteed after SIGKILL. This is not a raw-PCAP retention feature.

## Redacted artifacts

Raw capture stays inside a mode-0700 temporary directory on the worker. Before
SSH transfer the parser strips link-layer addresses and every payload, replaces
IPv4 addresses with 198.18.0.0/15 pseudonyms, zeroes IP/TCP options and transport
checksums, and converts timestamps to offsets from the first accepted packet.
The exported PCAP is an explicitly truncated IPv4 header projection, not a full
wire image. IPv4 checksums are recomputed; TCP/UDP checksums cannot be verified
without payload. All packets still expose their original IPv4 total length.

The parser supports classic PCAP, both byte orders and micro/nanosecond timestamps,
with Ethernet, raw IPv4, Linux cooked v1/v2 link types. Malformed/truncated input
fails closed. Unsupported/nonmatching/fragmented packets are excluded and counted.
PCAPNG and IPv6 are not supported by this first adapter.

The controller re-parses the projected PCAP, verifies its hash, flow totals and
absence of additional payload, and validates capture metadata against schema
1.0.0. Only then does it store redacted PCAP and CSV. Every download requires
authentication and a matching checksum bound to the immutable run record. Empty
or failed requested capture does not become a successful instrumented run.

The private run JSON includes the selected inventory/topology, which already
contains actual server addresses. The downloadable **PCAP/CSV** are the redacted
capture products. Do not treat the private inventory JSON as a public dataset.
Diagnostics use classified errors and a structured IP/credential redactor;
raw subprocess stderr, passwords and experiment tokens are not exported.

## Interpretation

The panel shows packets, IPv4 bytes, kernel drops (or unknown), excluded records,
flow tuples, and PCAP/CSV downloads separately for each capture host. IPv4 byte
counts include protocol headers and differ from echoed application bytes.
Vantage-point counts must not be summed as unique network packets. Capture drops,
retransmissions, snapshot truncation and reaching the packet limit do not by
themselves establish network packet loss. Cross-host clock synchronization and
one-way latency are not inferred.

## Verification

```sh
uv run --locked pytest tests/unit/test_capture.py tests/integration/test_capture_adapter.py
uv run --locked python scripts/synthetic_capture_example.py
```

The real adapter test runs only on Linux root with existing tcpdump; other hosts
skip that single test explicitly. Unit coverage includes link types, timestamps,
out-of-scope packets, payload/options/IP removal, malformed input and diagnostic
redaction. API coverage verifies authentication, checksums and empty-capture
failure. Actual multi-server acceptance is recorded separately after deployment.
