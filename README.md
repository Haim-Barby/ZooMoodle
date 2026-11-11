# ZooMoodle

A one-lesson teaching tool: the lecturer opens a lesson room, students join from their phones, and the lecturer sees who is in class, who is remote, and what the class thinks — notes, questions, polls, homework and an optional AI summary.

Individual project, Introduction to Software Engineering (OOP/OOD), Exercise 2. Deadline: 25 November 2026. Course used for the demo: **מערכות נוירונים, week 4, lecturer טום יניב**.

## The flow

**Lecturer**

1. Signs in with the lecturer key (a 256-bit random key). The page greets: *"שלום טום יניב, השבוע שבוע 4 בקורס מערכות נוירונים"*.
2. Opens a new lesson and imports the class list (CSV: first name, last name, email; an id-number column is ignored and never stored).
3. Shows two things on the projector: a **join QR** (opens the student site for this room) and the **live flickering barcode**.
4. Works from the room dashboard: in-class vs remote counts, the attendance list with ✓, a 3×3 class map, duplicate-name decisions, student notes, questions sorted by votes, polls with live results, homework upload, the lesson summary, and CSV/Excel export.

**Student (phone)**

1. Scans the join QR → picks their name from the list → chooses **בכיתה** or **מרחוק**. No id number and no email at entry.
2. **Remote:** marked remote at once. No network or barcode check.
3. **In class:** must pass both checks —
   - **University network.** The server reads the phone's real public IP and requires it to be inside the university ranges (default `192.114.48.0/21`, `192.114.56.0/23`). Body fields are ignored.
   - **Live barcode.** The camera is held on the flickering barcode for 2 seconds. A signed QR changes every 250 ms inside a 20 Hz shimmering border; the phone must collect ≥5 distinct codes. A screenshot (`qr_static`), a short capture (`qr_short`), a code older than 6 s by the server clock, a reused code, or a code from another room is rejected.
4. Picks their area in the classroom (3×3 map) → **✓ ברוך הבא ‹name›**.
5. From the phone: write a note, ask or up-vote a question, answer a poll, download homework, read the summary (or make a private one with their own API key).

**Duplicate names** are resolved in stages:

| Stage | Situation | What happens |
| --- | --- | --- |
| 1 | Same name chosen remotely and verified in class | In class wins; the remote entry is flagged for the lecturer. |
| 2 | Two verified in-class phones with one name | Both get a popup and re-pick their real name. |
| 3 | Still the same name | A 6-digit one-time code is e-mailed to that name's roster address; whoever types it gets the name (hashed, 5 min, 3 tries per phone, single use). |
| 4 | Still unresolved | The lecturer decides on the dashboard (and asks in class). |

## Privacy and security in one paragraph

The lecturer key is never committed or printed; the server keeps only an HMAC of it and hands the browser a short-lived session token. Each student phone gets its own session secret and signs every request (HMAC-SHA256, timestamp, nonce). Roster emails are kept as salted HMACs; the plain address lives only in server memory to send the duplicate-name code and never appears in any response, list or export. LLM API keys are used for one request and dropped — never stored, logged or returned.

## Run it

```bash
cd demo-web
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional settings, never committed
python -m app.main            # http://127.0.0.1:8000/
```

- On first start the lecturer key is created at `~/.zoomoodle/lecturer-key.txt` (mode 600). Only the path is printed. Paste the key on the lecturer page.
- Phones need **HTTPS** for the camera: `cloudflared tunnel --url http://127.0.0.1:8000`, and open the lecturer page through that URL so the join QR uses it.
- To try the in-class path at home, add your own address to `ZOOMODLE_CAMPUS_RANGES` in `.env` (for a local browser: `127.0.0.1/32`).
- Duplicate-name e-mail: set `ZOOMODLE_SMTP_*` in `.env`. `DEMO_EMAIL_OVERRIDE` routes every code to one demo inbox. With no SMTP the code is shown on the lecturer dashboard under **"מצב הדגמה – המייל לא נשלח"**.
- Tests: `python -m pytest -q` from `demo-web/`.

**Client IP behind a proxy.** Forwarded headers are trusted only from `ZOOMODLE_TRUSTED_PROXIES`. `CF-Connecting-IP` is accepted only from loopback (cloudflared on the same laptop). Otherwise the right-most `X-Forwarded-For` hop that is not a trusted proxy is used — on Render, the hop Render's proxy appended. A browser-supplied left-most hop is ignored. The assumption is that the platform proxy is the only path to the app.

**Render.** `demo-web/render.yaml` describes a free web service. Set `ZOOMODLE_MASTER_SECRET` and `ZOOMODLE_LECTURER_KEY` in the Render dashboard (an existing `ZOOMODLE_LECTURER_TOKEN` is accepted as the key). State is in memory: a restart or the free-plan spin-down clears lessons, so export the sheet before you finish.

## Assignment deliverables

| # | Item | File |
| --- | --- | --- |
| 1 | Problem and scope | this README |
| 2 | Tools report | [docs/02-tools-report.md](docs/02-tools-report.md) |
| 3 | Statement of work | [docs/03-SoW.md](docs/03-SoW.md) |
| 4 | Requirements and threat model | [docs/04-SRS.md](docs/04-SRS.md) |
| 5 | Use cases | [docs/05-use-cases.md](docs/05-use-cases.md) |
| 6 | Components | [docs/06-components.md](docs/06-components.md) |
| 7 | Class and sequence diagrams | [docs/07-design.md](docs/07-design.md) |
| 8 | Testing strategy | [docs/08-testing-strategy.md](docs/08-testing-strategy.md) |
| 9 | Demo app | `demo-web/` |
| 10 | 10-minute demo script | [docs/10-demo-script.md](docs/10-demo-script.md) |
| 11 | Conclusions | [docs/11-conclusions.md](docs/11-conclusions.md) |

**Not yet verified:** a real phone camera on the projected barcode, the university network as seen from Render, real SMTP delivery, and a live LLM call. The automated suite and a headless-browser run do not replace those checks.

Out of scope: Moodle/Zoom integration, university login, native apps, a database, face recognition.
