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
| Linux, Python 3.13, 15 Nov 2026 | `python -m pytest -q --cov=app` | 71 passed, 85% line coverage |
| Linux, in-process, 15 Nov 2026 | 150-student load test | ~10 ms per full check-in, 6 ms dashboard |
| Headless Chrome against a local server, 15 Nov 2026 | `tests/manual/browser_run.py`, `browser_duplicates.py` | sign-in, roster, live barcode (README GIF), two submissions, review error path; duplicate name → code → automatic decision → start over — as specified |
| Headless Chrome, 11 Nov 2026 | earlier manual run | in-class check-in with real screen codes, still-photo rejection, duplicate popup |

## 2. How the design changed

| Version | In-class proof | Why it changed |
| --- | --- | --- |
| 3 Nov | Ultrasonic FSK tone from the laptop + rotating QR | The tone was not decoded reliably from a projector speaker in a noisy room. |
| 8 Nov | Lecturer hotspot + local verifier, last 4 ID digits | Setup on every laptop; students lose Internet; ID digits are personal data a friend knows. |
| 11 Nov | **Campus network + live barcode** | The server decides the IP; the barcode cannot be passed on as a photo. Simple for the student: one scan. |
| 15 Nov | Same, scope trimmed | Removed the diagram endpoint and the private student summary; re-enabled the homework review that feature 5 asks for; duplicate names now end with a one-time code to the student's e-mail and are decided automatically (no lecturer step). |

## 3. Lessons learned

- **Design first paid off.** The first commits were the class and sequence diagrams and the test strategy. When the in-class proof changed twice, the rest of the design (rooms, roster, polls, agent) stayed, and the tests showed what broke.
- **Test a tool in real life before building on it.** The FSK beacon worked on paper and in unit tests but not in a classroom. The assignment's "test every tool in real life" rule is the lesson.
- **Vibe coding is fast, scope creep is faster.** An AI agent (Cursor Agent) produced working features in hours — and also features nobody asked for (e-mail codes, launchers, a diagram catalog). Reviewing every feature against the five assignment features, and deleting what did not serve them, was as important as writing code.
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
