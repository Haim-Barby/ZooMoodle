# Conclusions (draft)

## Built

The lesson flow is now one clear path: the lecturer signs in with a key and gets the course greeting, opens a lesson, and projects a join QR and a live flickering barcode. A student picks a name and chooses remote (no checks) or in class (university network **and** a 2-second live scan, then a classroom area). Duplicate names are handled in four stages, ending with the lecturer. The dashboard gathers counts, the list with ✓, the class map, conflicts, notes, questions, polls, homework and the summary.

Removed from earlier versions: the lecturer hotspot and local presence verifier with its launchers and range wizard, the ultrasonic FSK beacon, the device-key check-in, the email/ID confirmation at entry, the attention stub, pasted-source Q&A and LLM homework review. The agent's homework-review code remains in `app/llm/` but is not exposed.

## Results

| Environment | Command | Result |
| --- | --- | --- |
| Box VM, Python 3.13, 2026-11-11 | `python -m pytest -q` | 61 passed |
| Owner's Mac, 2026-11-11 | `python -m pytest -q` | see the PR description |
| Headless Chrome against a local server | manual Playwright script | sign-in, check-in, still-photo rejection, remote, poll/note/question/homework/summary, duplicate popup → code → lecturer all behaved as specified |

## Limits and remaining work

- Not yet tried with a real phone camera on a projector, on the real campus Wi-Fi through Render, with real SMTP, or with a live model.
- A live video relay to someone else on the campus network can still pass.
- An absent student's name can be used in class if nobody else claims it; the lecturer sees the list.
- Data is in memory; export before the server stops.

## Classroom results

| Item | Result | Notes |
| --- | --- | --- |
| Date, room, phones | | |
| Greeting | | |
| In class (Wi-Fi + scan) / off-campus refused / screenshot refused | | |
| Duplicate name stages | | |
| Poll, note, question, homework, summary | | |
| Export | | |
