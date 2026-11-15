# Conclusions

## 1. Results

All five assignment features are in the demo app:

| # | Feature | Result |
| --- | --- | --- |
| 1 | Attendance + spreadsheet | Two-factor in-class check-in (campus network + live barcode), remote join, automatic duplicate names (re-pick, then a one-time code to the student's Gmail), live dashboard, CSV/Excel export. |
| 2 | Comments | Notes, questions and up-votes from the phone. |
| 3 | Polls | Created in seconds, answered from the phone, live counts. |
| 4 | Lesson summary | Agent summary from the Zoom/Meet transcript plus polls and questions, published to the class. |
| 5 | Homework review | Student submission, LLM review with an anonymous similarity comparison, for the student or the lecturer. |

| Environment | Command | Result |
| --- | --- | --- |
| Linux, Python 3.13, 15 Nov 2026 | `python -m pytest -q --cov=app` | 73 passed, 85% line coverage |
| Linux, in-process, 15 Nov 2026 | 150-student load test | ~10 ms per full check-in, 6 ms dashboard |
| Headless Chrome against a local server, 15 Nov 2026 | `tests/manual/browser_run.py`, `browser_duplicates.py` | sign-in, roster, live barcode (README GIF), two submissions, review error path; duplicate name → code → automatic decision → start over — as specified |
| Headless Chrome, 11 Nov 2026 | earlier manual run | in-class check-in with real screen codes, still-photo rejection, duplicate popup |

## 2. How we reached the final check-in

The hardest question was how to prove "in class" (feature 1). We went through these stages before the campus-network check and the flickering barcode:

| Date | What we built | What we learned |
| --- | --- | --- |
| 3 Nov | An ultrasonic FSK tone from the lecturer's laptop to the phone microphone, together with a rotating QR; the lecturer chose the tone band, and the server issued each student's attendance id (commits `c0dd887`, `42c9ebf`, `3bf48c2`). | The tone was annoying in class and did not identify the room well. We started looking at Bluetooth and at the campus network instead. |
| 8 Nov | A personal Wi-Fi access point on the lecturer's laptop (Mac and Windows), with the network name and IP range typed by the lecturer, and a local verifier that checked the phone's real address against that range. A name got its ✓ only with the last 4 digits of the ID number and the verifier; double-click launchers started it (`65250d0`, `f854827`, `2c10ddf`). | macOS Internet sharing and the Windows adapter stayed manual steps on every laptop, students lost Internet while connected, and ID digits are personal data a friend may know. We also decided that being in the building is enough proof: a student in the building has no reason to skip the room. |
| 11 Nov, morning | The ID digits were dropped; the student confirmed with the e-mail from the class list (kept only as a salted HMAC). The rotating QR became a flickering, video-like barcode: the phone holds on it for 2 s, and both the decoded frames and the change between them are checked (`6e50409`). | A code that changes every 1–2 s can still be photographed and sent; a moving pattern held for 2 s cannot. |
| 11 Nov, midday | Rebuilt around two factors: the server reads the phone's public IP and requires the Ariel University ranges (`192.114.48.0/21`, `192.114.56.0/23`, checked in RIPE), plus the 2 s live barcode (signed 250 ms codes, single use). Nothing is typed at entry; the e-mail is used only for duplicate names. Lecturer key sign-in and a classroom area were added (`3842b85`). | Each factor is weak alone (a dorm is on the campus network, a friend can send a photo); together they mean "in the room", with one scan for the student. |
| 11 Nov, afternoon | The first run on Render refused the Ariel Wi-Fi: the server saw a Cloudflare address instead of the phone's. Fixed by reading `CF-Connecting-IP` from the trusted proxy (`808e863`). Poll delivery to phones was fixed the same day (`dad04b9`). | Test in the real deployment, not only locally. |
| 15 Nov | The scope was set to the five features: the homework review (feature 5) is on, the private student summary and a diagram endpoint are out, duplicate names are decided by a one-time code to the student's e-mail, and barcode codes must be at most 3 s old (`44a5ac5`, `08f47d6`, `6a147a1`). | Every feature was checked against the assignment. |

## 3. Lessons learned

- **Design first paid off.** The first commits were the class and sequence diagrams and the test strategy. When the in-class proof changed twice, the rest of the design (rooms, roster, polls, agent) stayed, and the tests showed what broke.
- **Test a tool in real life before building on it.** The FSK beacon passed its unit tests, but in a real room it was annoying and unreliable, and the campus check first failed on the real deployment. The assignment's "test every tool in real life" rule is the lesson.
- **Vibe coding is fast, scope creep is faster.** An AI agent (Cursor Agent) produced working features in hours — and also features nobody asked for (launchers, a diagram catalog, a private student summary). Reviewing every feature against the five assignment features, and deleting what did not serve them, was as important as writing code.
- **Combine weak factors instead of searching for one perfect one.** Neither the network nor the barcode is enough alone; together they are simple and hard to fake.
- **Keep the LLM on a short leash.** Read-only tools, pseudonyms, a required data-tool call and a validated report schema make the model's output checkable, and "not a grade" keeps it a helper, not a judge.

## 4. Limits and remaining work

- Not yet tried with a real phone camera on a projector, on the real campus Wi-Fi through Render, with real Gmail delivery, or with a live model (planned 16–23 Nov).
- A live video relay to someone else on the campus network can still pass.
- An absent student's name can be used in class if nobody else claims it; the lecturer sees the list and the class map.
- The lesson summary uses the transcript, not the video itself.
- The homework comparison is word-level similarity; it flags copying of text, not of ideas.
- Data is in memory; export before the server stops.

## 5. Classroom results

| Item | Result | Notes |
| --- | --- | --- |
| Date, room, phones | | |
| Greeting | | |
| In class (Wi-Fi + scan) / off-campus refused / screenshot refused | | |
| Duplicate name → Gmail code → automatic decision | | |
| Poll, note, question | | |
| Homework review, lesson summary (live model) | | |
| Export | | |
