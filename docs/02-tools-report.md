# Technical tools report

What was chosen for the demo, and what was actually run.

## Choices

| Concern | Candidates | Choice | Why |
| --- | --- | --- | --- |
| Backend | FastAPI, Flask, Django | FastAPI + Uvicorn | Small JSON API, file uploads, static pages, a test client. |
| Lecturer sign-in | Password, university SSO, random key | One 256-bit random key, HMAC-compared, exchanged for a session token | No account system needed; the key is never committed or printed. |
| In-class proof | GPS, own hotspot + local verifier, ultrasonic FSK, university network + live barcode | University network (server-side IP) + live flickering barcode | GPS is spoofable in the browser. A hotspot needs setup on every laptop. FSK was never verified from a speaker to a phone. The IP is decided by the server, and a live barcode defeats photos. |
| Barcode | Static QR, rotating QR, signed rotating QR with shimmer | Signed QR every 250 ms + 20 Hz shimmer, 2 s hold, ≥5 codes | Looks and behaves like video; a screenshot holds one code only. |
| QR in the browser | jsQR, ZXing, BarcodeDetector | jsQR (bundled) to read, own `qr.js` to draw | Works offline on iOS and Android browsers; no CDN. |
| Crypto | `hmac`, `cryptography` | HMAC-SHA256 + HKDF (`cryptography`) | Room keys, barcode MACs, session signing, hashed emails and codes. |
| Duplicate-name e-mail | Provider SDK, SMTP | `smtplib` with env settings, demo fallback | Works with any mailbox app password; nothing to install. |
| Spreadsheet | CSV, openpyxl, pandas | CSV + openpyxl | Enough for a lecturer sheet. |
| HTTPS for phones | cloudflared, ngrok, Render | cloudflared locally, Render for hosting | The phone camera requires a secure page. |
| LLM | One vendor SDK, small adapter | Adapter for OpenAI, Anthropic, Gemini, xAI (and compatible URLs) | The key is optional and given per request. |
| Tests | pytest, Playwright | pytest; Playwright + Chrome used once by hand | API and logic in CI; a real browser for the pages. |
| Diagrams | PlantUML, drawing tool | PlantUML sources with SVG exports | Text diffs in git. |

## What was run

- `pytest` from `demo-web/`: see [conclusions](11-conclusions.md) for the count.
- A headless Chrome run against a local server: lecturer sign-in and greeting, open lesson, roster import, live barcode drawn, a student page signing its own requests, live codes accepted → area → "ברוך הבא", a frozen code rejected (`qr_static`), remote join, poll/note/question/homework/summary, and the full duplicate-name path (re-pick popup → e-mail code in demo mode → lecturer reject). The camera was replaced by feeding the page the codes that were really on the lecturer screen.

## What was not run

- A real phone camera pointed at a projector.
- A phone on the university Wi-Fi reaching Render (to confirm the public IP range that Render sees).
- Real SMTP delivery.
- A live LLM call.

## Classroom results (owner)

| Check | Device | Result | Notes |
| --- | --- | --- | --- |
| Join QR opens the HTTPS student page | iPhone / Android | | |
| On campus Wi-Fi: in-class allowed; on cellular: refused | | | |
| 2 s live scan → area → ✓ ברוך הבא | | | |
| Screenshot of the barcode rejected | | | |
| Duplicate name → popup → e-mail code | | | |
| Poll, note, question, homework, summary | | | |
