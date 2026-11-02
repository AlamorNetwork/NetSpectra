# ADR-002 — Selected multi-server experiments

Status: implemented foundation; external acceptance and review tracked separately.

## Decision

The operator requested real inter-server measurements instead of treating local
loopback success as evidence of network quality. The authenticated controller
maintains a versioned inventory and immutable named topologies. Each experiment
selects client nodes, backend nodes, and an optional load-balancer node. The
controller itself can be registered as a worker with a separate role.

Without a load balancer the runner measures the Cartesian product of selected
clients and servers. With a load balancer, selected clients connect to a temporary
round-robin TCP/UDP lab relay, which forwards to the selected backends. The relay
is a lab instrument, not an HAProxy/nginx production service or an HTTP benchmark.
Clients and backends may share a node; direct self-pairs are excluded from both
the plan and execution. The relay must have its own node. Two nodes suffice for
a client/backend node communicating through a separate relay. The inventory supports 32 nodes; a topology
supports up to 8 clients, 8 backends, and one relay.

SSH carries installation/control commands only. Synthetic test packets travel
directly between selected node addresses; there is no SSH data tunnel. Local
engine tests remain available and are visibly separate from network results.

## Installation and existing workloads

Each worker is installed by Git into a **new** dedicated `/opt/netspectra-*` or
`/srv/netspectra-*` directory. An existing directory, including an earlier worker
checkout, is never overwritten or cleaned. Missing `git`/`python3` are reported;
the worker itself needs no pip packages, system package installation or global
Python changes. A failed partial clone is left for the operator to inspect;
select another new directory before retrying. Updating a node's SSH address/port
invalidates its host-key pin. Node settings are editable through the panel.

OpenSSH uses explicit identity, BatchMode and strict pinned-host verification.
The controller generates its own key; it never copies an existing personal
private key to another server. The public key must first be authorized on each
worker. Host-key scanning proposes a candidate; it does not automatically trust
it. Previously verified SSH host keys can be imported over a trusted connection.

No service is stopped to free a port. The bounded listener binds normally and
fails with `port_in_use` if occupied. No firewall rules, routing configuration,
existing application folders or unrelated services are changed. Test ports are
explicitly selected in 28000–28999. Listeners last at most 60 seconds and terminate
when their SSH control input closes; the controller reaps its SSH subprocesses.
The runner has a 60-second total deadline and at most ten payloads per path.

For the supplied Iran server (`87.107.146.217`, SSH port 9011), work is restricted
to a newly created dedicated folder. Existing Phoenix folders must not be edited.
Changing `/root/.ssh/authorized_keys` is a separate exception to that restriction
and requires the operator's explicit agreement; an existing trusted laptop SSH
identity can perform initial installation without that exception.

## Results and scope

Network runs use a separate versioned artifact with topology/node snapshots,
controller provenance, agent provenance, workload hash, per-sample backend identity,
echoed bytes and application round-trip time. A checksum sidecar detects later
artifact changes. Partial completed paths survive a later path failure. The UI
does not call local integration tests evidence of Iran-to-Europe connectivity.

The temporary worker accepts selected peer IPs and a random per-run token.
Payloads are synthetic and bounded to 512 bytes. NAT/source address differences
can cause peer rejection and need explicit inventory/routing design; this first
version assumes each node's advertised address is reachable from the others.
Larger concurrent load, arbitrary traffic, TLS/QUIC/HTTP measurements, cross-server
replay, capture and namespace impairment remain follow-on work.
