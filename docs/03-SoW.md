# Statement of work

ZooMoodle, Exercise 2, individual project. Deadline: 25 November 2026.

## Objective

A working design and a ten-minute classroom demo of a lesson tool whose main feature is trustworthy attendance, plus notes, questions, polls, homework files and an optional AI summary.

## Scope

In: lecturer key sign-in with the greeting, lesson rooms, roster import, join QR, the live flickering barcode, the university-network check, remote join, classroom area, staged duplicate-name resolution (popup → e-mail code → lecturer), the lecturer dashboard, CSV/XLSX export, polls, notes, questions, homework upload and download, transcript import and an optional LLM summary.

Out: Moodle/Zoom integration, university login, native apps, a database, face recognition, grading.

## Work sequence

1. Problem, scope and tools — done.
2. Requirements, use cases, components, design, tests — done.
3. Demo application and automated tests — done.
4. Real phones on campus Wi-Fi, SMTP delivery, live model — owner, before the demo.
5. Classroom demo and conclusions — owner.

## Assumptions

- One server process; data is in memory and lost on restart.
- Phones reach the server over HTTPS (Render or a tunnel).
- Campus Wi-Fi leaves the university through `192.114.48.0/21` / `192.114.56.0/23`, and the server sees that address.
- The lecturer keeps the key private.

## Risks

| Risk | Response |
| --- | --- |
| Campus egress differs from the configured ranges | Ranges are an env setting; test with a phone before class. |
| Student uses cellular data in class | The page tells them to switch to the campus Wi-Fi or join remotely. |
| A classmate live-streams the barcode from a dorm on the campus network | Possible; the network range narrows it to campus, and duplicate names go to the lecturer. |
| Camera blocked without HTTPS | Use Render or cloudflared. |
| SMTP not available | Demo mode shows the code on the lecturer dashboard. |
| Server restarts | Export the sheet before finishing. |

## Acceptance

- Wrong lecturer key → refused; right key → the greeting.
- In class needs both the campus network and a 2 s live scan; a screenshot or an off-campus IP is refused.
- Remote join needs neither.
- Duplicate names follow the four stages; the lecturer can always decide.
- No id number is stored; emails and API keys never appear in responses, exports or logs.
- All automated tests pass; classroom results are recorded in the tools report.
