# Dorsal 1.5

The bottom bar is plainer: it stays empty unless you have changes that aren't
applied yet, then it says "Not applied" with an Apply button.

Diagnostics reads the mouse afresh: 30 timed read-command exchanges and eight
configuration checks, with a comparison against the editor. Results include
timestamps, missing responses and unavailable fields instead of assumed passes.

Live input runs for 15 seconds and reads the mouse's polling/DPI configuration
before capture. It reports Windows movement-event rate, arrival intervals and
button repeats. This does not measure USB-bus timing or click-to-screen latency.
Estimated power/current figures have been removed from the UI.

Install **Dorsal-Setup-1.5.exe**, or extract the portable zip. Existing settings
are kept. See [Diagnostics](DIAGNOSTICS.md) for measurement methods and limits.
