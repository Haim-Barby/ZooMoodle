from tests.conftest import make_client


def test_pages_are_hebrew_and_have_no_legacy_flow():
    _app, client = make_client()
    lecturer = client.get("/").text
    student = client.get("/student").text
    assert 'dir="rtl"' in lecturer and 'dir="rtl"' in student
    assert "מפתח מרצה" in lecturer and "פתח שיעור חדש" in lecturer and "live-frame" in lecturer
    assert "בכיתה" in student and "מרחוק" in student and "jsqr.js" in student
    for text in (lecturer, student):
        lowered = text.lower()
        for legacy in ("fsk", "hotspot", "ultrasonic", "presence helper", "דוא״ל שלך"):
            assert legacy not in lowered
    js = client.get("/static/student.js").text
    assert "x-zoomoodle-signature" in js and "/barcode" in js and "/repick" in js and "/email-code" in js
    assert client.get("/static/fsk.js").status_code == 404
