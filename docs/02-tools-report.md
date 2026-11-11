# Technical tools report

Tool choices for the demo, and what was actually run. Physical phone-camera scanning, a real lecturer hotspot, an HTTPS tunnel from a phone, and a live model call have not been performed.

## Choices

| Concern | Candidates | Choice | Why |
| --- | --- | --- | --- |
| Backend | FastAPI, Flask, Django | FastAPI + Uvicorn | Small JSON API, uploads, and static pages. A hello route was run. |
| In-class presence | Flickering signed QR, ultrasonic FSK, GPS | Flickering signed QR plus a local HTTP verifier | A still photo is not enough, and the helper checks the real socket peer on the lecturer's network. GPS is easy to spoof. jsQR decodes frames in the phone browser. |
| Data over sound | ggwave, custom FSK | Optional legacy path only: custom 18/19 kHz FSK | Kept in the demo as a tab, not required for the roster checkmark. File-level encode/decode was run; speaker-to-phone reception was not. |
| Room crypto | `hmac` only, or `cryptography` HKDF | HKDF-SHA256 and HMAC-SHA256 | Matches the room-key, roster email confirmation, and barcode-frame design. Round trips ran in tests. |
| Local verifier | Client-claimed IP/SSID, or a bound helper | Helper bound to the hotspot address | Reads the socket peer and rejects public ranges, ranges wider than /24, `0.0.0.0`, and forwarded headers. |
| Lecturer launchers | Fully automatic hotspot, or a saved setup | macOS `.command` and Windows `.bat` | After `~/.zoomoodle/lecturer-setup.json` exists, one double-click starts the helper. They do not fully provision a hotspot. |
| Spreadsheet | CSV only, openpyxl, pandas | CSV and openpyxl | Both writers ran. Pandas is more than this demo needs. |
| HTTPS tunnel | cloudflared, ngrok | cloudflared, documented, not run here | Phone camera (and the optional microphone) need a secure context. |
| LLM | One vendor SDK, or a small adapter | Adapter for OpenAI, Anthropic, Gemini, xAI, Ollama, and OpenAI-compatible URLs | The lecturer picks the provider. No live call was made. Tests use mocked or scripted providers. |
| Transcript | Live Zoom/Meet API, file import | UTF-8 file import | The assignment does not require Zoom integration. |
| Automated tests | pytest, Playwright | pytest | **103 passed** on the owner's Mac, from `demo-web/`. The suite includes roster, barcode-liveness, and helper-range tests. It is not a physical camera or hotspot trial. |
| Diagrams | PlantUML, Graphviz-only, a drawing tool | PlantUML sources plus SVG | Rendered with Java and Graphviz when that toolchain is available. |
| Attention / head pose | MediaPipe, a manual stub | Stub only | MediaPipe was spiked on a VM with no camera. The demo does not claim to see the room. |

Demo dependencies are pinned in `demo-web/requirements.txt`. ggwave, MediaPipe, and NumPy were spike-only and are not demo dependencies.

## What was run

On a development VM (Python 3.12): FastAPI hello; HKDF/HMAC room tokens; CSV/XLSX writers; PlantUML; a MediaPipe blank-image spike (no face); and an FSK file round-trip at 18/19 kHz, including a simulated 3400 Hz voice-band cut that dropped the payload. ggwave encoded in a different band, so it was not selected. Those outputs are preserved in the earlier long form of this report and in [conclusions](11-conclusions.md). They were file or library checks, not a phone in a room.

On the owner's Mac: the demo test suite reported **103 passed**, including synthetic roster import, confirmation lockout, flickering-barcode liveness (`qr_static`, `qr_short`, stale, replay, wrong room), and a real TCP socket whose peer was outside the configured range. Launchers were tested as a plan, without changing a network.

## What was not run

- A real iPhone or Android camera on the flickering barcode
- A real macOS Internet Sharing or Windows Mobile Hotspot session
- cloudflared or ngrok from a phone
- A live LLM provider call
- Speaker-to-phone FSK

## Classroom results (owner)

Fill after physical trials. Automated tests do not close these checks.

| Check | Device / place | Result | Notes |
| --- | --- | --- | --- |
| Camera permission and HTTPS student page | iPhone Safari | | |
| Camera permission and HTTPS student page | Android Chrome | | |
| Two-second live barcode, then checkmark and welcome | | | At least five distinct frames |
| Still photo or screenshot rejected (`qr_static`) | | | |
| Lecturer hotspot and helper range | macOS / Windows | | Entered verifier address and /24 range |
| Phone on the hotspot reaches the helper | | | Claimed IP/SSID must not be enough |
| Remote row stays separate, with no roster checkmark | | | |
| Export opens | | | |
| Test connection with a real key | lecturer laptop | | |
| Lesson agent and homework review | | | |
