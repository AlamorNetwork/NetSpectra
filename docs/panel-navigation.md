# Panel navigation

The sidebar separates network operations from the local engine:

| Page | Fragment | Purpose |
| --- | --- | --- |
| سرورها | #servers | SSH identity, nodes, bootstrap, dependencies and preflight |
| مسیرهای آزمایش | #paths | Client/backend/protocol configuration and starting runs |
| نتایج بین سرورها | #network-results | Network history, sample details, PCAP/CSV and qlog |
| تست محلی | #experiments | Local engine configurations and runs |
| نتایج محلی | #runs | Local engine history and replay |
| راهنمای کار | #guide | Operator guidance |

Each page has its own heading and selected menu state. Only the chosen workspace
is visible. Browser Back/Forward and direct fragments work. The legacy #cluster
fragment resolves to #servers. Skip-to-content keeps the current workspace.
Starting a network run opens its results workspace; the active job banner remains
visible above the current page. Preparation operations do not expose a cancellation
button that their worker does not implement.

Paths support name/server search, protocol filtering and eight items per page.
Network results support name/run-ID search, status filtering and ten items per
page. Filters survive navigation within the loaded panel and reset on reload;
pagination counts describe the currently loaded history, not an archival total.
No inventory or historical runs are removed by filtering or pagination.

At <=800px the sidebar becomes a collapsible menu with aria-controls/aria-expanded.
Selecting a page closes it; Escape closes it and restores focus to its trigger.
The desktop sidebar remains visible. Existing theme, typography and report dialogs
are retained.

Verification: real browser checks covered workspace separation, path pagination,
empty search, result filtering, opening an authentic report, Back navigation and
legacy links against the local authenticated preview. A 390px-wide static fixture
using the same frontend assets covered mobile expansion, selection/collapse and
Escape. The production panel's frame protections were retained. Nine panel API
integration tests, JavaScript syntax checks, Ruff/format, unique HTML ID/menu
destination checks and source/wheel builds passed. Screenshots and fixture files
remain in ignored local artifacts.
