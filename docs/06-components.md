# Software components

One Python process, two static pages, no database. Arrows in the diagram are call direction.

![Components](diagrams/components.svg)

Source: `docs/diagrams/components.puml`.

## Browser

| Component | Responsibility | Talks to |
| --- | --- | --- |
| Lecturer page (`lecturer.html/js`) | Key sign-in and greeting, open lesson, roster import, join QR, live barcode (QR + shimmer canvas), dashboard, conflict buttons, polls, homework upload, summary, export. | `/api/...` with `X-Lecturer-Session`. |
| Student page (`student.html/js`) | Name list, בכיתה/מרחוק, camera scan, area map, re-pick popup, code entry, note/question/poll, homework download, summary. | `/api/...`, every call after join signed with the session key (HMAC, timestamp, nonce). |
| `qr.js` / `jsqr.js` | Draw QR codes / decode camera frames. | Local only. |

## Server (`demo-web/app/`)

| Component | Responsibility | Interface |
| --- | --- | --- |
| HTTP API (`main.py`) | Routes, lecturer/student auth, JSON errors, file responses. | REST under `/api`. |
| `LecturerAuth` | HMAC of the lecturer key, rate limit, session tokens. | `sign_in`, `check`, `sign_out`. |
| `Settings` (`config.py`) | Env and key file, campus ranges, SMTP, greeting. | `from_env`. |
| `Store` / `Room` | In-memory rooms, polls, notes, questions, homework files, summary; agent snapshot with names removed. | Methods on `Store`. |
| `RoomRoster` | CSV import, salted email HMAC, in-memory address for the code. | `replace_from_csv`, `public_names`, `get`, `email_for`. |
| `CheckinBook` | Claims, network + barcode gate, area, duplicate stages, e-mail challenges, lecturer decisions. | `join`, `submit_barcode`, `choose_area`, `repick`, `submit_code`, `decide`. |
| `ScreenQrService` | Issue and verify signed 250 ms codes and the shimmer seed. | `issue`, `verify_sequence`. |
| `net.client_ip` | Real client IP behind trusted proxies; range match. | `client_ip`, `subnet_status`. |
| `SessionBook` | Per-phone session secrets and signed-request verification. | `issue`, `verify`. |
| `Mailer` | SMTP send of the one-time code, demo override, demo fallback. | `send_code`. |
| `ExportService` | CSV/XLSX sheet. | `to_csv`, `to_xlsx`. |
| `SummaryService` / `LessonAgent` / `LLMClient` | Tool-calling summary from polls, notes, questions and transcript. | `summarize`. |

## External

- **Mail server** (SMTP, optional) — receives the one-time code.
- **LLM provider** (optional) — called only when someone supplies a key.
- **Render / cloudflared** — HTTPS in front of the app; the proxy appends the client IP.
