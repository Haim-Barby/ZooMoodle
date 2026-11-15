import re

from tests.conftest import make_client

PAGE_SCRIPTS = {"/static/qr.js", "/static/jsqr.js", "/static/lecturer.js", "/static/student.js"}


def test_pages_are_hebrew_and_show_only_the_checkin_flow():
    _app, client = make_client()
    lecturer = client.get("/").text
    student = client.get("/student").text
    assert 'dir="rtl"' in lecturer and 'dir="rtl"' in student
    assert "מפתח מרצה" in lecturer and "פתח שיעור חדש" in lecturer and "live-frame" in lecturer
    assert "בכיתה" in student and "מרחוק" in student and "jsqr.js" in student
    # The pages load only the four scripts of this flow.
    for text in (lecturer, student):
        scripts = set(re.findall(r'<script[^>]*\ssrc="([^"?]+)', text))
        assert scripts and scripts <= PAGE_SCRIPTS, scripts
    # No e-mail or ID is typed at entry.
    assert "דוא״ל שלך" not in student and "תעודת זהות" not in student
    js = client.get("/static/student.js").text
    assert "x-zoomoodle-signature" in js and "/barcode" in js and "/repick" in js and "/email-code" in js
