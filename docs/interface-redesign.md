# Interface redesign acceptance

The interface-design brief and reusable decisions live in `.interface-design/system.md`.
The Persian RTL workbench uses charcoal surfaces, mint actions, restrained borders,
local Vazirmatn fonts and native disclosure controls.

- Servers: identity and SSH endpoint first; setup actions progressively disclosed.
- Paths: visible client/relay/backend roles, protocol and live form preview.
- Reports: outcome and measurements first; qlog, captures and identifiers in separate disclosures.
- Network and local experiments retain separate navigation and bounded result pages.
- No online state is inferred from a saved SSH host key. Missing timing stays missing.

Verified locally against an authenticated copy of redacted controller state:
server settings, path preview, relay constraints, failed QUIC report, qlog and PCAP downloads.
Responsive navigation is additionally checked in a 390px fixture, not a live server session.
Ruff, panel integration tests, JavaScript syntax and wheel build are checked before publication.
This visual change does not close the W04 network acceptance gate.
