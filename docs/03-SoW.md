# Statement of work

ZooMoodle, Exercise 2, individual project. Deadline: 25 November 2026.

## 1. Objective

Design, and demo in class in 10 minutes, a simple phone-based teaching tool whose main feature is **trustworthy attendance with a spreadsheet**, plus comments, polls, an LLM lesson summary and an LLM homework review with comparison (the five features of the assignment).

## 2. Scope

**In**

| Feature | Included |
| --- | --- |
| 1. Attendance | Lecturer key sign-in with the course greeting, lesson rooms, roster CSV import, join QR, two-factor in-class check-in (campus network + live barcode), remote join, classroom area, duplicate-name resolution (re-pick, then a one-time code the lecturer types on the real student's phone), live dashboard, CSV/XLSX export |
| 2. Comments | Notes and questions from the phone, question up-votes |
| 3. Polls | 2–6 options, optional correct answer, live counts, close |
| 4. Summary | Transcript upload, LLM agent summary (or a manual one) published to the class |
| 5. Homework review | Student submission, LLM review with anonymous comparison to other submissions, for the student or the lecturer |
| Extra | Homework file upload/download by the lecturer |

**Out:** Moodle/Zoom integration, university login or personal-data systems, native apps, a database, face recognition, grading.

## 3. Deliverables and schedule

| # | Deliverable | Planned | Status |
| --- | --- | --- | --- |
| 1 | Repository, problem and scope (README) | 3 Nov | Done |
| 2 | Tools report, incl. real-life checks | 3–15 Nov | Done; real-life table in class |
| 3 | SoW (this document) | 3 Nov | Done |
| 4 | SRS + threat model | 3 Nov | Done |
| 5 | Use cases / client stories | 3 Nov | Done |
| 6 | Components | 3 Nov | Done |
| 7 | Class, state and sequence diagrams | 3 Nov | Done |
| 8 | Testing strategy | 3 Nov | Done |
| 9 | Demo web app (campus network + live barcode, features 1–5) | 3–15 Nov | Done |
| — | Real phones on campus Wi-Fi, the lecturer-code step, live LLM, fill the tools report | 16–23 Nov | Owner |
| — | Submission | 25 Nov | |
| 10 | Classroom demo | Lesson after submission | Owner |
| 11 | Conclusions with classroom results | After the demo | Draft done |

## 4. Assumptions

- One server process; data is in memory and lost on restart.
- Phones reach the server over HTTPS (Render or a tunnel).
- Campus Wi-Fi leaves the university through `192.114.48.0/21` / `192.114.56.0/23`, and the server sees that address.
- The lecturer keeps the key private. LLM keys are brought per request by whoever uses the AI features.

## 5. Risks

| Risk | Likelihood | Response |
| --- | --- | --- |
| Campus egress differs from the configured ranges | Medium | Ranges are an env setting; test with a phone before class (16–23 Nov). |
| Student uses cellular data in class | High | The page tells them to switch to campus Wi-Fi or join remotely. |
| A classmate live-streams the barcode to a dorm on the campus network | Low | Accepted residual; the lecturer sees the list and the class map. |
| Camera blocked without HTTPS | Medium | Use Render or cloudflared. |
| A slow upload makes the 2 s capture older than 3 s | Medium | The phone sends the codes right after the hold; on a stale result it starts a new scan. Test on the campus Wi-Fi (16–23 Nov). |
| No LLM key available in the demo | Medium | Manual summary path; features 4–5 shown with a prepared key. |
| Server restarts (Render free plan sleeps) | Medium | Open the site before class; export the sheet before finishing. |

## 6. Acceptance

- Wrong lecturer key → refused; right key → the greeting.
- In class needs both the campus network and a 2 s live scan with codes at most 3 s old; a screenshot or an off-campus IP is refused. Remote join needs neither.
- Duplicate names: re-pick, then a one-time code on the lecturer dashboard; the phone it is typed on gets the name and the other phone is removed (it can check in again with another name); a wrong code is refused and a code works once; the lecturer can still accept or reject by hand.
- The sheet downloads as CSV and Excel with name, mode, state, area and time — no e-mail and no ID.
- A student can comment, ask, vote, answer a poll, submit homework and get a review from the phone.
- All automated tests pass; real-life results are recorded in the tools report.
