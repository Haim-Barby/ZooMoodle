from io import BytesIO

from openpyxl import load_workbook

from app.domain import AttendanceRecord
from app.export_svc import ExportService


def _record():
    return AttendanceRecord(
        student_id="s1",
        student_name="Ada",
        device_id="abcd1234abcd1234",
        mode="in_class",
        seat_zone="front-left",
        at=1_700_000_000,
        confidence="high",
        flags=["late_token"],
        subnet="match",
        token_late=True,
    )


def test_csv_and_xlsx_contain_the_same_columns():
    service = ExportService()
    csv_text = service.to_csv([_record()]).decode("utf-8")
    assert csv_text.splitlines()[0] == "student_id,name,mode,seat_zone,time_utc,confidence,flags,subnet,device_id"
    assert "s1,Ada,in_class,front-left," in csv_text
    assert ",high,late_token,match,abcd1234abcd1234" in csv_text

    book = load_workbook(BytesIO(service.to_xlsx([_record()])))
    sheet = book["Attendance"]
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    assert headers[0] == "student_id"
    assert headers[5] == "confidence"
    values = [cell.value for cell in next(sheet.iter_rows(min_row=2, max_row=2))]
    assert values[1] == "Ada"
    assert values[6] == "late_token"
