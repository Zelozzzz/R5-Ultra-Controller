# Diagnostics

**Run diagnostics** performs read-only inspection. It does not apply the editor's
settings, install firmware, remap buttons or change Competitive Mode.

## Device inspection

- Times 30 alternating battery/firmware requests from send to matching response.
  Reports answered commands, receiver-only responses, other misses, median and
  p95 round-trip time. These are settings-channel measurements, not RF signal
  strength, USB report loss or click latency.
- Reads firmware, battery, polling rate, six X/Y DPI stages, active DPI stage,
  lift-off distance, debounce, motion sync, ripple control and Competitive Mode.
- Compares settings against the editor snapshot taken before the run. A difference
  can mean unapplied edits; it does not by itself mean a hardware fault.
- Records time, duration, selected profile, connection and read failures. Missing
  values are unavailable, never an inferred Off or Pass. A connection/profile
  change marks the snapshot stale. Later setting edits require another inspection.
- Lists other known mouse applications by process name. Their presence suggests
  possible interference; it does not establish that they are using the device.

The firmware version does not identify the LED patch: both stock and patched
images can report the same version. The battery percentage is read from the device;
remaining time and drain are estimates. The mouse does not report voltage/current.

## Input capture

Capture runs for 15 seconds. Keep the mouse moving in circles for a rate test;
click each button to inspect its press and rapid-repeat counts. Capture can be
stopped early. Leaving Diagnostics stops the listener and cancels a pending start.

The listener filters Windows Raw Input by the R5 Ultra vendor/product IDs.
It measures movement-event arrivals with a monotonic clock. Rate samples use
100 ms movement windows; gaps over 20 ms start a new window. At least ten windows
are needed for rate comparison. Interval percentiles exclude those idle gaps.
Absolute coordinates are excluded from the relative-motion calculation.

Windows can queue or coalesce events, so these observations are not a USB-bus
trace. No input at rest is normal. Low movement rate alone does not diagnose
packet loss. The DPI and polling comparison use fresh device readbacks at capture
start, not unsaved values in the editor. Speed is an estimate from relative counts
and DPI, available only when a readable stage has equal X/Y DPI. A repeat within
25 ms of release is flagged for investigation; intentional clicks and macros can
produce it, so it is not proof of a mechanical switch fault.

Implementation references: [Microsoft Raw Input overview](https://learn.microsoft.com/en-us/windows/win32/inputdev/about-raw-input)
and [RAWMOUSE event definitions](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-rawmouse).

## Export

Copy report exports the readable summary. JSON includes inspection evidence,
command samples and retained input intervals; CSV contains numeric sample series.
Samples are bounded in memory (2,048 movement windows and 8,192 intervals).
