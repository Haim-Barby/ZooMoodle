# Use cases

Actors: Lecturer, Student, Mail server, LLM provider.

## UC-1 Lecturer signs in
I enter my key and see "שלום טום יניב, השבוע שבוע 4 בקורס מערכות נוירונים".
**Accept:** wrong key → 401, 10 failures → 429; the key is not echoed; lecturer routes need the session token.

## UC-2 Lecturer opens a lesson
I open a lesson, import the roster, and project the join QR and the live barcode.
**Accept:** the roster shows names only; the barcode changes every 250 ms and shimmers.

## UC-3 Student joins remotely
I scan the join QR, pick my name, choose מרחוק.
**Accept:** ✓ remote and "ברוך הבא ‹name›"; no network or barcode needed.

## UC-4 Student checks in from class
I pick my name, choose בכיתה, hold my camera on the barcode for 2 s, then pick my area.
**Accept:** refused off the campus network (`not_on_campus_network`); a screenshot → `qr_static`; too short → `qr_short`; stale, reused or other-room codes refused; a valid scan → area → ✓ and "ברוך הבא ‹name›"; forged forwarding headers do not help.

## UC-5 Duplicate name
Two phones claim one name.
**Accept:** remote vs verified in class → remote flagged. Two in class → both see a re-pick popup. Same name again → an e-mailed code; the right code takes the name, the other goes to the lecturer. Wrong codes or expiry → the lecturer decides. Without SMTP the code appears only on the dashboard as "מצב הדגמה – המייל לא נשלח".

## UC-6 Lecturer decides
I see the conflict on the dashboard, ask in class, and press "זה הוא" or "דחה".
**Accept:** the accepted claim gets the name; other claims for that name are rejected.

## UC-7 Poll
I open a poll; students answer once from the phone.
**Accept:** the dashboard shows live counts; students see counts after voting or when closed.

## UC-8 Notes and questions
Students send notes and questions and up-vote questions.
**Accept:** the dashboard shows notes with names and questions sorted by votes; only checked-in students can post.

## UC-9 Homework
I upload a file; students download it.
**Accept:** lecturer-only upload, ≤5 MB; download requires a checked-in session and is served as an attachment.

## UC-10 Lesson summary (optional)
I upload a transcript and either write a summary or give a provider, model and API key.
**Accept:** the summary appears to all students of the room; a student may make a private one with their own key; keys are never stored, logged or returned.

## UC-11 Export
I download the attendance sheet.
**Accept:** CSV/XLSX with name, mode, state, area, time; no email or id.
