# ZooMoodle

A simple, LLM-ready web tool for one lesson at a time: attendance that is hard to fake, and a clear picture of which material and which part of the room lost the class.

Individual course project for Introduction to Software Engineering (OOP/OOD), Exercise 2. This file defines the problem and the scope. Nothing in it is implemented or tested yet.

## Problem

Current online tools for teaching are not doing the job. Courses need simpler tools that support learning in the room and that are ready for large language models.

Two gaps drive this project:

- **Attendance is easy to fake.** A student can check in from elsewhere, share a code, or have a classmate do it. The lecturer then has a list, with little sign of who was actually in the room.
- **Feedback is late and coarse.** Lecturers rarely see, during the lesson or just after it, which material lost the class and which area of the room stopped following.

ZooMoodle is a small set of tools that stay inside a single lesson. Students use a phone browser. Summaries and homework review can use an LLM later, without connecting to Moodle, Zoom, or personal-information systems.

## Goal

Design an end-to-end web application a lecturer can run in this class and show in a real demo of about ten minutes. The design stays simple enough to implement. For attendance, the honest aim is to make faking hard and noticeable, not impossible.

## Scope

### In scope

Each lesson is a **Room**. The lecturer opens a room for that lesson only. The room has its own cryptographic key, derived from the lecturer's master secret and a room-specific random salt (for example with HKDF). Attendance, polls, comments, and a later transcript all belong to that room.

- **Attendance (core — must work flawlessly in the demo).**
  - The lecturer's computer broadcasts a short-lived, signed one-time token as a near-ultrasonic signal (about 18–20 kHz).
  - The student's phone receives it through the microphone in the web app (Web Audio API). Audio is chosen over Bluetooth because it works in ordinary browsers on iPhone, Android, Mac, and laptops. Web Bluetooth is not supported on iOS Safari.
  - The token is an HMAC over the room id, a rotating time window, and a nonce. It is valid for only a few seconds and is single-use.
  - Further checks: the device is on the university-network subnet; one device is bound to one student (a device key stored on first use); a challenge-response with a latency check resists relaying the sound over a call or a recording (phone and VoIP codecs typically cut these high frequencies).
  - If audio fails, the lecturer can show a short rotating code on screen.
  - A remote participant presses "I'm joining remotely" and receives a separate external token, so the sheet keeps in-class and remote apart.
  - Anomalies are flagged for the lecturer: the same student or device on both lists, two students from one device, or a late token.
  - The lecturer gets an online sheet and an offline export (CSV or XLSX) with the details and a confidence level.
- **Seat zone.** At check-in the student picks a zone on a simple classroom map: front, middle, or back, and left or right.
- **Comments and suggestions**, during the lesson or afterwards. Minimal, and working in the demo.
- **On-the-spot polls.** The lecturer asks a short question about the material just covered. Results can be viewed by seat zone. Minimal, and working in the demo.
- **Attention map (stretch).** One camera facing the class computes an anonymous attention indicator per zone over time (for example head pose with open-source MediaPipe). There is no face recognition and no per-student tracking. Frames are not stored; only zone aggregates are kept. The map is an indicator for the lecturer, not a grade. Designed in full; implemented only as a stretch.
- **AI lesson summary (stretch).** After class the lecturer imports a transcript file from a Zoom or Google Classroom recording. There is no live integration. The report combines the transcript with poll results by zone and, when present, the attention map, and points to the topic, time, and zone that lost attention or answered wrongly, so the next lesson can focus there. Designed in full; implemented minimally.
- **LLM homework review (stretch).** Students and the lecturer can request a deep review of homework, including an anonymized comparison with other students' work. Designed in full; implemented minimally.

### Out of scope

- Integration with Moodle, Zoom, Google Classroom, or any personal-information system. A recording enters only as a file the lecturer imports.
- Storing personal or biometric data, face recognition, and tracking a student on video.
- Native iOS or Android applications. Students use a web app in the phone browser.
- Treating the attention map as a grade, or any feature that cannot be implemented for a short in-class demo.

## Key features

| Priority | Feature | Demo intent |
| --- | --- | --- |
| P0 | Room, plus attendance (ultrasonic token, device binding, remote vs in-class, export with confidence) | Must work flawlessly |
| P1 | Seat zone on a simple map | Part of check-in |
| P1 | Comments and suggestions, live or later | Minimal, working |
| P1 | On-the-spot polls, results by zone | Minimal, working |
| P2 | Anonymous attention map by zone | Designed fully; stretch to build |
| P2 | AI lesson summary from an imported transcript | Designed fully; minimal build |
| P2 | LLM homework review with anonymized comparison | Designed fully; minimal build |

## Requirements and constraints

- It must work in this class and be shown in a real demo of about ten minutes.
- Keep it simple (KISS). Students use a simple web application on a smartphone.
- No integration with Moodle, Zoom, or personal-information systems.
- Design only what can be implemented. The demo may be composed from existing code; writing everything from scratch is not required.
- The same browser flow should run on common phones and laptops.
- This stage is design only: problem and scope. Later documents and the demo are still to come.

## Planned deliverables

- [x] 1. Create a repository and define the problem and the scope in the README.
- [ ] 2. Technical tools report, with each suggested tool tried in real use.
- [ ] 3. Statement of Work (SoW).
- [ ] 4. Software Requirements Specification (SRS).
- [ ] 5. Main use cases (client stories).
- [ ] 6. Main software components.
- [ ] 7. Low-level class diagrams and sequence diagrams.
- [ ] 8. Testing strategy, including the classes from item 7.
- [ ] 9. Implement a simple demo web application (vibe-coded, or found and composed).
- [ ] 10. Demo in class (about ten minutes).
- [ ] 11. Conclude the assignment with a short description of the results.

## Privacy and security principles

- Each lesson gets its own key, derived from the lecturer's master secret and a fresh salt. Tokens are short-lived, single-use HMACs bound to that room.
- One student is bound to one device. A device key is stored on first use and identifies that binding afterwards.
- In-class and remote presence use different tokens and stay in separate rows. Odd patterns are flagged for the lecturer to review.
- If an attention map is built, it keeps zone aggregates only: no faces, no identities, and no saved video frames. It is an indicator, not a grade.
- Homework comparison is anonymized. The tool does not take identity data from university personal-information systems.
- The attendance export is for the lecturer of that room and includes a confidence level. The design makes cheating difficult and visible; it does not claim to make cheating impossible.
