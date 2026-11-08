"""Room roster import and a weak last-four identity check.

The national id and email from the CSV are not stored. The last four digits
are kept only as an HMAC under the server master secret and a per-person salt.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import os
import secrets
import time
from dataclasses import dataclass, field

PIN_WINDOW_SECONDS = 600
PIN_LIMITS = {"entry": 5, "ip": 20, "attempt": 10}

HEADER_GIVEN = "שם פרטי"
HEADER_FAMILY = "שם משפחה"
HEADER_ID = "מספר זיהוי"
HEADER_EMAIL = 'דוא"ל'
HEADER_GROUP = "קבוצות"
REQUIRED_HEADERS = (HEADER_GIVEN, HEADER_FAMILY, HEADER_ID, HEADER_EMAIL, HEADER_GROUP)


class RosterError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _norm_header(value: str) -> str:
    text = (value or "").replace("\ufeff", "").strip()
    return text.replace("״", '"').replace("“", '"').replace("”", '"')


def pin_mac(master: bytes, salt: bytes, entry_id: str, pin: str) -> bytes:
    message = salt + b"|" + entry_id.encode("utf-8") + b"|" + pin.encode("ascii")
    return hmac.new(master, message, hashlib.sha256).digest()


@dataclass
class RosterEntry:
    id: str
    given: str
    family: str
    group: str
    salt: bytes
    verifier: bytes

    @property
    def display(self) -> str:
        return f"{self.given} {self.family}".strip()


@dataclass
class RateLimiter:
    clock: object = time.time
    hits: dict = field(default_factory=dict)

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = float(self.clock())
        recent = [stamp for stamp in self.hits.get(key, []) if now - stamp < window]
        self.hits[key] = recent
        return len(recent) < limit

    def add(self, key: str, window: float) -> None:
        now = float(self.clock())
        recent = [stamp for stamp in self.hits.get(key, []) if now - stamp < window]
        recent.append(now)
        self.hits[key] = recent


def parse_roster_csv(text: str) -> tuple[list[dict], dict]:
    """Return rows ready to seal, plus counts. Full ids and emails are not returned."""
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise RosterError("roster_headers")
    mapped = {_norm_header(name): name for name in reader.fieldnames if name}
    missing = [header for header in REQUIRED_HEADERS if header not in mapped]
    if missing:
        raise RosterError("roster_headers")
    rows: list[dict] = []
    seen: set[str] = set()
    stats = {"imported": 0, "duplicates": 0, "skipped": 0, "groups": {}}
    for raw in reader:
        given = (raw.get(mapped[HEADER_GIVEN]) or "").strip()
        family = (raw.get(mapped[HEADER_FAMILY]) or "").strip()
        national = "".join((raw.get(mapped[HEADER_ID]) or "").split())
        group = (raw.get(mapped[HEADER_GROUP]) or "").strip()
        if not given and not family and not national and not group:
            stats["skipped"] += 1
            continue
        if not given or not family or not national.isdigit() or len(national) < 4:
            stats["skipped"] += 1
            continue
        digest = hashlib.sha256(national.encode("ascii")).hexdigest()
        if digest in seen:
            stats["duplicates"] += 1
            continue
        seen.add(digest)
        rows.append({"given": given, "family": family, "last4": national[-4:], "group": group})
        stats["groups"][group] = stats["groups"].get(group, 0) + 1
    stats["imported"] = len(rows)
    return rows, stats


class RoomRoster:
    def __init__(self, master: bytes, clock=None):
        if not master:
            raise ValueError("master secret is empty")
        self.master = master
        self.entries: dict[str, RosterEntry] = {}
        self.selected_group: str | None = None
        self.include_unspecified = False
        self.limiter = RateLimiter(clock or time.time)

    def replace_from_csv(self, text: str) -> dict:
        rows, stats = parse_roster_csv(text)
        sealed: dict[str, RosterEntry] = {}
        for row in rows:
            entry_id = secrets.token_hex(8)
            salt = os.urandom(16)
            verifier = pin_mac(self.master, salt, entry_id, row["last4"])
            sealed[entry_id] = RosterEntry(
                id=entry_id,
                given=row["given"],
                family=row["family"],
                group=row["group"],
                salt=salt,
                verifier=verifier,
            )
        self.entries = sealed
        self.selected_group = None
        self.include_unspecified = False
        return {
            "imported": stats["imported"],
            "duplicates": stats["duplicates"],
            "skipped": stats["skipped"],
            "groups": dict(stats["groups"]),
        }

    def select_group(self, group: str | None, include_unspecified: bool) -> dict:
        if include_unspecified:
            self.selected_group = None
            self.include_unspecified = True
        else:
            if group is None or str(group).strip() == "":
                raise RosterError("group_required")
            self.selected_group = str(group).strip()
            self.include_unspecified = False
        return {"group": self.selected_group or "", "include_unspecified": self.include_unspecified, "listed": len(self.public_names())}

    def _selected(self, entry: RosterEntry) -> bool:
        if self.include_unspecified:
            return entry.group == ""
        if self.selected_group is None:
            return False
        return entry.group == self.selected_group

    def public_names(self) -> list[dict]:
        chosen = [entry for entry in self.entries.values() if self._selected(entry)]
        chosen.sort(key=lambda entry: (entry.family, entry.given, entry.id))
        return [{"id": entry.id, "display": entry.display} for entry in chosen]

    def lecturer_rows(self, in_class: dict, remote: dict) -> list[dict]:
        rows = []
        for entry in sorted(self.entries.values(), key=lambda item: (item.family, item.given, item.id)):
            rows.append(
                {
                    "id": entry.id,
                    "display": entry.display,
                    "group": entry.group,
                    "in_class": bool(in_class.get(entry.id)),
                    "remote": bool(remote.get(entry.id)),
                }
            )
        return rows

    def check_pin(self, entry_id: str, pin: str, ip: str, attempt: str) -> RosterEntry:
        keys = (
            ("entry:" + (entry_id or ""), PIN_LIMITS["entry"]),
            ("ip:" + (ip or "unknown"), PIN_LIMITS["ip"]),
            ("attempt:" + (attempt or "none"), PIN_LIMITS["attempt"]),
        )
        for key, limit in keys:
            if not self.limiter.allow(key, limit, PIN_WINDOW_SECONDS):
                raise RosterError("identity_limited")
        entry = self.entries.get(entry_id or "")
        candidate = (pin or "").strip()
        if entry is None or not self._selected(entry) or len(candidate) != 4 or not candidate.isdigit():
            dummy = pin_mac(self.master, b"\x00" * 16, "none", "0000")
            hmac.compare_digest(dummy, b"\x00" * 32)
            ok = False
        else:
            got = pin_mac(self.master, entry.salt, entry.id, candidate)
            ok = hmac.compare_digest(got, entry.verifier)
        if not ok:
            for key, _limit in keys:
                self.limiter.add(key, PIN_WINDOW_SECONDS)
            raise RosterError("identity_rejected")
        return entry
