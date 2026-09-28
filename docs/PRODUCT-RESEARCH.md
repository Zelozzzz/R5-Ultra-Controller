# Mouse software workflow research

Reviewed September 27, 2026 against official product/support documentation. These
are workflow references, not claims that Dorsal supports another mouse's hardware.

| Reference | Useful pattern | Dorsal 1.10 decision |
| --- | --- | --- |
| [Logitech G HUB onboard memory](https://support.logi.com/hc/en-nz/articles/6505257646743-Enable-On-Board-Memory-mode-on-your-gaming-mouse-with-Logitech-G-HUB) | Select and save a specific onboard profile | Label the header Onboard 1–3 and name the save destination |
| [Razer Synapse 4 profiles](https://mysupport.razer.com/app/answers/detail/a_id/13863/~/how-to-create-mouse-profiles-on-razer-synapse-4) | Separate the profile library from onboard assignment | Keep local setups distinct from the active hardware profile; warn before replacing pending edits |
| [Corsair iCUE Device Memory Mode](https://www.corsair.com/ca/en/explorer/gamer/mice/how-to-set-up-device-memory-mode-dmm-in-icue/) | Make persistence and save actions explicit | Review pending fields, Save to mouse, then verify supported readbacks |
| [SteelSeries Aerox onboard memory](https://support.steelseries.com/hc/en-us/articles/15250138269837-Aerox-Mice-Onboard-Memory) | Explain which functions persist after the app exits | Label static lighting versus animated effects that require Dorsal running |
| [Pulsar Windows software](https://support.pulsar.gg/hc/en-us/articles/58623651313689-How-to-use-the-mouse-Windows-software) | Direct access to DPI, debounce and sensor controls | Preserve the focused Home layout; improve keyboard operation rather than add another settings layer |
| [Razer macro configuration](https://mysupport.razer.com/app/answers/detail/a_id/1483/kw/the%20new%20synapse) | Explicit recording and timing controls | Preserve sequence editing, expose saved/unsaved state and explain shared onboard slots |

## Design decisions

Retain the existing translucent workspace, mouse illustration and restrained
navigation. Use a compact action bar only for pending changes. Dense measurements
use stable columns, tabular numbers and readable surfaces. Feedback belongs close
to the action and must remain accessible to keyboard and screen-reader users.

Diagnostics are evidence, not a synthetic health score: fresh device reads,
command response timing, and a guided 15-second Windows input capture. A previous
inspection can be compared on the same profile and connection type, without
claiming that a small timing difference proves improved latency. Speed estimates
are suppressed after a detected configuration change.

## Deliberate limits

The bulk save verifies DPI, polling, lift-off, debounce, motion sync, ripple,
angle snap and sleep. Lighting uses acknowledgements because patched firmware's
brightness readback is not reliable. Command round-trip time is not click latency.
No sensor calibration, battery current, radio RSSI or surface-quality score is
invented where the protocol does not expose one.
