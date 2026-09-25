# EkaDrishti DJI Mission Capture Checklist

## Required upload package

1. The original DJI `.MP4` flight video. Do not trim, re-encode, or rename it before copying the matching sidecar file.
2. The matching original DJI `.SRT` telemetry file, captured by the same flight.

EkaDrishti rejects a missing, empty, or unreadable SRT because geographic coordinates, map placement, and field measurements depend on flight telemetry.

## Capture rules for a usable building model

- Fly slowly with the camera fixed; do not use fast pans or abrupt turns.
- Record in 4K where possible and lock exposure and focus before takeoff.
- Cover the site with 70–80% forward overlap and at least 60% side overlap.
- Make one nadir pass (camera facing down) for a map-like surface.
- Make additional oblique passes around building sides for facades and height.
- Avoid moving vehicles, people, trees in strong wind, and reflective/glass-dominant scenes where possible.
- Keep a safe, legal altitude and retain the original MP4 and SRT together.

## Judge explanation

“EkaDrishti accepts the original DJI video and its flight-telemetry sidecar as one mission package. Visual overlap reconstructs the 3D geometry; SRT telemetry geo-references it for map navigation and inspection. We reject incomplete input rather than presenting uncalibrated visual artifacts as survey data.”

## Important limitation

SRT gives camera position and timing. It does not itself create building geometry. A complete 3D building model still requires overlapping views around the building, especially oblique facade passes.
