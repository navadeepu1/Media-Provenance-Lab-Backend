# Browser accessibility and workflow test

The local interface was tested on Windows in the VS Code integrated browser on
November 3, 2026 using the running application.

| Area | Result |
|---|---|
| Keyboard-visible focus styling | Pass |
| Synthetic sample buttons are reachable and activate analysis | Pass |
| Progress status and progress bar are exposed while running | Pass |
| Cancellation control is reachable and sends a cancellation request | Pass |
| Final report status, uncertainty panel, signal table, and heatmaps render | Pass |
| Report images expose descriptive alternative text | Pass |
| API/network failures expose an alert region | Covered by automated DOM tests |
| 360px responsive layout | Covered by automated CSS regression tests |

This is a browser workflow check, not certification for every screen reader or
browser combination. A release should repeat it with a native screen reader
such as Narrator or NVDA and record the browser/version used.
