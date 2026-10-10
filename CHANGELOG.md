# Changelog

## v0.1.0-preview.1 — 2026-10-10

Development preview for ESP-Mosaico V1.2 / ESP32-S31 and DJI Osmo Pocket 3.

**Prebuilt firmware: ESP-Mosaico hardware V1.2 only. Do not flash it onto V1.0 or other boards.**

- Add explicit V1.2 board pins and the tested PSRAM XIP boot profile.
- Recognize observed Pocket 3 advertisements and valid control-heartbeat variants.
- Reduce OpenH264 initial bitstream reservation while retaining checked growth.
- Keep preview visible in HEAD and JOYSTICK; preserve stop confirmation and require a fresh gesture after a recoverable control pause.
- Retain accepted preview requests across temporary writer gates.
- Test a TX A-MPDU-disabled profile for small control/ACK traffic, keeping RX aggregation and safety deadlines.
- Handle a precisely matched, one-byte preview E1 reply as a failed request eligible for the existing bounded timeout recovery. Unknown/rejected replies and startup ENABLE keep their previous failure behavior.
- Add bounded fault diagnostics, host regression coverage, portable SDK path selection and version-specific verification documentation.

### Verification and limitations

The published application has passed full device readback, protected-prefix comparison and 80 on-board startup checks. Host regression groups pass. A directly preceding image received user acceptance for repeated five-second joystick operation, release-to-stop and concurrent preview; the released E1 branch has not yet been observed recovering from a real camera E1 response.

Long-running preview can still freeze, suffer fragment loss or encounter heartbeat/Flow ACK faults. This is a prerelease snapshot, not a full-function or long-duration stability certification. See [verification details](docs/mosaico-full-bench.md).
