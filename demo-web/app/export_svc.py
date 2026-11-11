"""CSV and XLSX attendance sheets for the lecturer. No email, no id number."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from openpyxl import Workbook

COLUMNS = ("name", "mode", "status", "area", "time_utc")


def _time(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(value: str) -> str:
    text = str(value or "")
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


class ExportService:
    def rows(self, students: list[dict]) -> list[list[str]]:
        return [
            [_safe(s["name"]), s["mode"], s["state"], s["zone"], _time(s["at"])]
            for s in students
        ]

    def to_csv(self, students: list[dict]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(COLUMNS)
        writer.writerows(self.rows(students))
        return ("\ufeff" + buffer.getvalue()).encode("utf-8")

    def to_xlsx(self, students: list[dict]) -> bytes:
        book = Workbook()
        sheet = book.active
        sheet.title = "attendance"
        sheet.append(list(COLUMNS))
        for row in self.rows(students):
            sheet.append(row)
        out = io.BytesIO()
        book.save(out)
        return out.getvalue()
