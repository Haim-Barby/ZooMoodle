# Technical tools report

What was considered, what was chosen, what was written by an AI agent ("vibe-coded") and what was taken ready-made ("composed"), and what was tested in real life.

## 1. The key decision: how to prove "in class"

This was the main design question (feature 1), so several tools were tried before the final choice.

| Candidate | Tried? | Result | Kept? |
| --- | --- | --- | --- |
| Photo of the class + automatic head count (assignment example) | Considered | Gives *how many*, not *who*; needs a vision model per lesson; a count alone cannot fill a named sheet. | No — our sheet is per student. A head count stays a possible add-on. |
| GPS / browser location | Considered | Location is easy to fake in the browser; indoor accuracy is poor. | No |
| Ultrasonic FSK beacon (laptop speaker → phone mic) | Built (commit `c0dd887`) | Never decoded reliably from a projector speaker to a phone in a noisy room. | Removed |
| Lecturer hotspot + local verifier | Built (commits `65250d0`–`2c10ddf`) | Needs setup on every lecturer laptop; students lose Internet while connected. | Removed |
| Last 4 digits of the ID number | Built, then removed | Personal data; a friend knows it. | Removed |
| **University network (server-side IP) + live barcode** | **Built and kept** | IP is decided by the server, not the phone; a 250 ms signed QR cannot be passed on as a photo. Together: on campus **and** looking at the screen. | **Yes** |

## 2. Tool choices

| Concern | Candidates | Choice | Why |
| --- | --- | --- | --- |
| Backend | FastAPI, Flask, Django | FastAPI + Uvicorn | Small JSON API, uploads, static pages, a built-in test client. |
| Front end | React, plain HTML/JS | Plain HTML + JS, RTL Hebrew | KISS: no build step, opens on any phone browser. |
| Lecturer sign-in | Password, university SSO, random key | One 256-bit random key → short session token | No account system (guideline 1). |
| QR in the browser | jsQR, ZXing, BarcodeDetector | jsQR (bundled) to read, own `qr.js` to draw | Works on iOS and Android, offline, no CDN. |
| Crypto | `hmac`, `cryptography` | HMAC-SHA256 + HKDF | Room keys, barcode signatures, request signing, hashed e-mails. |
| Duplicate-name one-time code | SMS, provider SDK (SendGrid), SMTP | `smtplib` over **Gmail SMTP** (`smtp.gmail.com:587`, App Password), demo fallback on the dashboard | Students already have the e-mail from the class list; Gmail is free and needs nothing installed. |
| Spreadsheet | CSV, openpyxl, pandas | CSV + openpyxl | Enough for the lecturer's sheet (online = dashboard, offline = file). |
| HTTPS for phones | cloudflared, ngrok, Render | Render for hosting, cloudflared locally | The phone camera needs a secure page. |
| Video summary input | Video file → speech-to-text, Zoom/Meet transcript | **Transcript file (VTT/TXT)** | Zoom/Meet already export it; uploading a 1-hour video and running speech-to-text is slow and costly. The summary uses the transcript *plus* polls and questions, which Zoom's own summary does not see. |
| LLM | One vendor SDK, small adapter | Own adapter: OpenAI, Anthropic, Gemini, xAI, compatible URLs | The lecturer or student brings any key; no vendor lock-in. |
| Homework comparison | Embeddings, LLM-only, token similarity | Jaccard similarity as a tool + LLM review | Deterministic, free, explainable; the LLM explains the numbers. |
| Tests | pytest, Playwright | pytest (71 tests) + a Playwright browser run | API and logic in the suite; the real pages in Chrome. |
| Diagrams | PlantUML, drawing tool | PlantUML sources + SVG exports | Text diffs in git. |

## 3. Vibe-coded vs. composed

The assignment prefers composing existing code over writing everything. The split:

| Part | How | Notes |
| --- | --- | --- |
| Web framework, server, ASGI | **Composed** — FastAPI, Uvicorn, Starlette | |
| QR decoding on the phone | **Composed** — jsQR (bundled `jsqr.js`, ~10k lines) | Largest single piece of code in the repo. |
| Crypto primitives, Excel writer, HTTP client | **Composed** — `cryptography`, `openpyxl`, `httpx` | |
| LLM vendors | **Composed** — their public REST APIs | Wrapped by our own Adapter (`providers.py`). |
| Domain logic: check-in states, duplicate names, barcode signing and liveness, client-IP rules, agent loop and tools | **Vibe-coded** — written with an AI coding agent (Cursor Agent, 3–8 Nov; later commits 11–15 Nov), reviewed and tested by me | This is the design-specific part; nothing ready-made does it. |
| QR drawing (`qr.js`) and the shimmer border | **Vibe-coded** | Small; a library would add a CDN dependency. |
| Documents and diagrams | Written by me with AI help | Design came first (diagrams and test strategy were the first commits). |

## 4. What was run

- `python -m pytest -q` from `demo-web/`: **71 passed**, 85% line coverage (15 Nov 2026).
- Headless Chrome (Playwright) against a local server: lecturer sign-in and greeting, open lesson, roster import, live barcode drawn and recorded (the README GIF), two students join remotely, both submit homework, the lecturer sees the submissions, a student review without a key shows "חסר מפתח API". Script: [`demo-web/tests/manual/browser_run.py`](../demo-web/tests/manual/browser_run.py).
- Headless Chrome, duplicate names: two phones check in class as "דנה לוי" with the codes really shown on the lecturer screen → both get the re-pick popup → both pick the same name → "אימות במייל" with a code box; the lecturer dashboard shows the code (demo mode) → phone A types it → "ברוך הבא דנה לוי"; phone B → "לא אושר" + "התחל מחדש"; dashboard 1 in class, 0 conflicts. Script: [`demo-web/tests/manual/browser_duplicates.py`](../demo-web/tests/manual/browser_duplicates.py).
- Earlier headless run (11 Nov): a frozen code rejected (`qr_static`).

## 5. Real-life checks

The assignment asks to test every tool in real life. To be filled in class before the demo:

| Check | Device | Result | Notes |
| --- | --- | --- | --- |
| Join QR opens the HTTPS student page | iPhone / Android | | |
| Campus Wi-Fi: in class allowed; cellular: refused | | | |
| 2 s live scan → area → ✓ ברוך הבא | | | |
| Screenshot of the barcode rejected | | | |
| Duplicate name → popup → one-time code arrives in Gmail → right code wins | | | |
| Poll, note, question from the phone | | | |
| Lesson summary from a real Zoom transcript (live model) | | | Compare with Zoom's own summary |
| Homework review on the course's example repos (live model) | | | |
