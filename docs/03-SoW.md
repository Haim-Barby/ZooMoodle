# Statement of work

ZooMoodle, Introduction to Software Engineering, Exercise 2. Individual project. Deadline: 25 November 2026.

## Objective and scope

Deliver an implementable design and a ten-minute classroom demo of a teaching tool. Attendance is the priority. Students use a phone web page; the lecturer uses a laptop.

The demo covers lesson rooms, combined in-class attendance (imported roster and email confirmation, a two-second live flickering barcode, and a local network verifier), a roster checkmark and welcome, separate remote attendance, seat zones, CSV/XLSX export, comments, polls, transcript import, and lesson/homework agents. Model configuration and a connection test support the agents. Full requirements are in the [SRS](04-SRS.md). The [README](../README.md) maps deliverables 1–11 to their files.

An older ultrasonic FSK path remains in the UI as an optional tab and is not required for the checkmark. The attention extension uses labeled sample aggregates only. Native apps, university accounts, a durable database, live camera processing, and integrations with university systems are outside this demo. Converting recordings to transcripts is an external prerequisite.

## Work sequence and status

1. Define the problem, scope, and tool choices — written; VM and Mac tests recorded.
2. Specify requirements, use cases, components, classes, sequences, and testing — documents and diagrams present.
3. Compose the demo and run automated tests — implemented; 103 tests passed on the owner's Mac.
4. Validate a real phone camera, a real hotspot, HTTPS from a phone, and a live model — pending.
5. Give the classroom demo and complete the final results — pending.

## Assumptions

- A single process holds lesson data in memory. Restarting clears rooms.
- Phones reach the app through an HTTPS origin (tunnel or Render). The local verifier runs on the lecturer laptop, on the hotspot, not through that origin.
- Barcode freshness uses the server clock. A live video relay from a classmate may pass liveness; the network check is what requires the lecturer's network.
- Launchers start a saved helper setup. They do not fully turn on Internet Sharing or Mobile Hotspot.
- A lecturer-supplied model is required for the agents. Tests use scripted responses. Known names are redacted on the agent path, with limits in the SRS.

## Principal risks

| Risk | Response and remaining limit |
| --- | --- |
| Phone camera or HTTPS blocks the barcode scan | Requires a secure origin; untested on real phones. A still photo must not pass. |
| Hotspot setup is manual, especially on a Mac | Documented steps and launchers; a failed helper means no checkmark. |
| A classmate live-streams the lecturer screen | Liveness may pass; the local range check covers a student off the network. Relay from a phone already on the hotspot remains possible. |
| Model unavailable or invalid | Connection test, read-only tools, report validation; return an error, not a substitute report. |
| Process stops | Export attendance before shutdown; the demo has no recovery. |

## Acceptance

- Lecturer authentication gates room creation, roster and presence settings, attendance, exports, configuration, and lecturer AI actions.
- A student can pick a name from the imported list, confirm with that email, complete a two-second live barcode capture, reach the local verifier, and then receive a checkmark and welcome. A still photo, a short capture, a stale or reused code, or a peer outside the configured range does not mark the roster.
- Remote attendance stays a separate row, without a roster checkmark.
- CSV and XLSX are lecturer-only and do not include a national id or the raw email.
- Without model configuration, AI routes return a configuration error. With a tool-calling provider, agents must read data before a validated report; homework reviews require `not_a_grade: true`.
- Completion requires recorded classroom and live-model results, not just written plans. Use the [demo script](10-demo-script.md) and fill the results table in the tools report.
