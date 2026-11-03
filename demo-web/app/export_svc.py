"""CSV and XLSX attendance sheets for the lecturer."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from openpyxl import Workbook

from app.domain import AttendanceRecord

COLUMNS = (
    "student_id",
    "name",
    "mode",
    "seat_zone",
    "time_utc",
    "confidence",
    "flags",
    "subnet",
    "device_id",
)


def _time(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows(records: list[AttendanceRecord]) -> list[list[str]]:
    table = []
    for record in records:
        table.append(
            [
                record.student_id,
                record.student_name,
                record.mode,
                record.seat_zone,
                _time(record.at),
                record.confidence,
                ";".join(record.flags),
                record.subnet,
                record.device_id,
            ]
        )
    return table


class ExportService:
    def to_csv(self, records: list[AttendanceRecord]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows(records))
        return buffer.getvalue().encode("utf-8")

    def to_xlsx(self, records: list[AttendanceRecord]) -> bytes:
        book = Workbook()
        sheet = book.active
        sheet.title = "Attendance"
        sheet.append(list(COLUMNS))
        for row in rows(records):
            sheet.append(row)
        buffer = io.BytesIO()
        book.save(buffer)
        return buffer.getvalue()
