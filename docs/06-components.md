# Software components

The demo is one Python process, two static pages, and a small local helper on the lecturer laptop. Arrows in the diagram are call direction.

![Components](diagrams/components.svg)

Source: `docs/diagrams/components.puml`.

## Browser

| Component | Responsibility | Interface |
| --- | --- | --- |
| Lecturer page | Unlock, open a room, import a roster, show the flickering barcode, enter network name / verifier address / range, sheet, export, polls, transcript, agent, attention samples, LLM form. | `fetch` to `/api/...` with `X-Lecturer-Token`. |
| Flickering barcode | Draw the signed QR about every 250 ms and a ~20 Hz shimmer from the server seed. | Lecturer page canvas plus the current-frame API. |
| Student page | Name list, email confirmation, two-second camera scan, then the network step; poll, comment, homework. | Public POST routes for identify, barcode submit, and finish. |
| Camera / QR decoder | Hold the camera on the live pattern, decode distinct frames, submit the batch. | getUserMedia and jsQR. HTTPS is required. |
| Local presence helper | Accept `/prove` only on the bound hotspot address if the socket peer is in range; tell the server; redirect the phone. | HTTP on the lecturer laptop, not on Render. |

An optional FSK player and microphone decoder remain in the pages as a legacy tab. They are not part of the checkmark path.

The lecturer token lives in `sessionStorage` on that browser. Provider keys are not stored in the browser after the request.

## Server

| Component | Responsibility | Interface |
| --- | --- | --- |
| HTTP API (`app/main.py`) | Routes, lecturer-token check, error JSON. | REST under `/api`. |
| Room store | In-memory rooms, polls, comments, homework, transcript, names. Builds the agent snapshot with names removed. | Methods on `Store`. |
| KeyManager | HKDF room key from the master secret and the room salt. | `derive_room_key(salt) -> 32 bytes`. |
| RoomRoster (`app/roster.py`) | Import minimization, group filter, salted email check, lockout. | Import, list names, verify email. |
| ScreenQrService (`app/screen_qr.py`) | Issue frames, verify liveness, freshness, single-use, and room binding. | Current frame, submit sequence. |
| Network range (`app/network_range.py`) | Validate verifier address and client CIDR (≤ /24, not public). | Parse and contain. |
| Presence helper (`app/presence.py`) | Observe a challenge only from a real in-range socket on the bound address. | `/prove`, server `observe`. |
| AttendanceService | Challenges, redemption, confidence, checkmark only after the required proofs. | `check_in` / finish presence. |
| DeviceBinding / AnomalyDetector | First key per device; rewrite flags after each check-in. | `observe`, `apply`. |
| ExportService | CSV and XLSX bytes, without a national id or the raw email. | `to_csv`, `to_xlsx`. |
| AttentionAggregator | Zone samples labeled `sample-not-camera` only. | `add_sample`, `by_zone`. |
| LessonAgent, tools, LLMClient | Tool loop, report validation, provider adapters. | `run`, `complete`, `test_connection`. |

LLM adapters (OpenAI, Anthropic, Gemini, xAI, Ollama, OpenAI-compatible) and key handling are unchanged: the key is a header only, never a query string, and is omitted from responses. Adapter defaults and header names live in `app/llm/providers.py`.

## What is deliberately not a component

- A database, a queue, a user directory, Moodle, Zoom, and a camera pipeline that recognizes faces.
- MediaPipe. It was spiked and is not imported by `app/`.
- A cloud presence verifier. The helper runs on the lecturer laptop.
