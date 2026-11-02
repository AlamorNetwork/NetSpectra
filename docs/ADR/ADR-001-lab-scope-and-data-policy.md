# ADR-001: Lab scope, consent and sensitive data

- Date: 2026-10-31
- Status: Proposed for independent review
- Roadmap: PPRL-M01-W01-T06

## Context

PPRL measures protocol behavior under controlled impairment. Measurements may
reveal addresses, timing, identifiers and payloads. A failed handshake alone
does not establish deliberate interference. W01 currently has structural data
contracts and fixed loopback smoke probes; a complete isolation or privacy
enforcement engine does not yet exist.

## Decision

1. Default to synthetic traffic and lab-owned endpoints. The initial Experiment
   contract accepts only isolated / synthetic_only scope. W01 probes bind and
   connect exclusively to IPv4 loopback, using ephemeral ports and fixed bytes.
   Later active probes must have an explicit lab allowlist, traffic budgets,
   deadlines, stop/cancellation and cleanup behavior before use.
2. Do not enable real-user data collection merely by changing a schema value.
   Any future consented mode needs reviewed consent records describing purpose,
   data fields, retention, access, withdrawal and deletion. External endpoints
   require ownership or explicit permission. No Internet-wide scanning.
3. Minimize collection. Do not collect real-user TLS keys or application payloads.
   Keep secrets in an environment/key manager, outside Git and logs. Error reports
   should expose safe categories rather than sensitive exception messages.
   Existing parent-directory VPN files are outside this repository and scope.
4. Raw captures are not published by default. Explicit raw retention inside the
   lab does not authorize upload/publication. Future retention must have a time
   limit, access controls and deletion handling. Public exports need review,
   identifier/payload removal and re-identification assessment. Datasets have
   their own provenance, consent scope and redistribution terms.
5. Preserve evidence and uncertainty: observed / derived / hypothesis / unknown.
   Register controls, seeds, tool versions, source revisions and artifact hashes.
   Never label an unknown result as confirmed censorship. Report failures and
   alternatives. Published claims remain limited to the measured conditions.

## Consequences and limits

- Loopback smoke runs require no privileged network configuration. Namespace,
  routing, allowlist and fail-closed controls are future W05 work; loopback
  success is not evidence that arbitrary lab processes cannot reach the Internet.
- WSL installation and dependency downloads may access the Internet; that setup
  traffic is separate from the synthetic measurement workload.
- Schema validation cannot enforce network scope, consent, data deletion,
  artifact content or safe filesystem resolution. Each needs implementation and
  evidence before the corresponding capability is enabled.
- Privacy/RBAC/export controls are planned work, not completed functionality.
  Do not accept production data into placeholders.

## Evidence and review gate

Contract tests reject unsupported scope. Integration tests exercise local TCP/UDP
echo, timeout cleanup and cancellation cleanup. Hosted Ubuntu/Windows CI runs
the same smoke. Real-data modes and broader network scope need a new or amended
ADR, privacy review and independent reproduction before activation.

Independent reviewer and approval: pending. This document records the proposed
baseline; it does not claim external approval.
