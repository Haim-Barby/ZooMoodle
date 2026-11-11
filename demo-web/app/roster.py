"""Room roster import and email confirmation.

The national id from the CSV is ignored and not stored. The email is kept
only as an HMAC under the server master secret and a per-person salt.
Plain email is never stored or returned.
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

IDENTITY_WINDOW_SECONDS = 600
IDENTITY_LIMITS = {"entry": 5, "ip": 20, "attempt": 10}

GIVEN_ALIASES = frozenset({"שם פרטי", "first name", "given name", "given", "firstname", "first"})
FAMILY_ALIASES = frozenset({"שם משפחה", "last name", "family name", "family", "lastname", "surname", "last"})
NAME_ALIASES = frozenset({"שם", "name", "full name", "student name"})
EMAIL_ALIASES = frozenset({"דואל", "email", "e-mail", "e mail", "mail"})
GROUP_ALIASES = frozenset({"קבוצות", "קבוצה", "group", "groups"})


class RosterError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _norm_header(value: str) -> str:
    text = (value or "").replace("\ufeff", "").strip()
    return text.replace("״", '"').replace("“", '"').replace("”", '"')


def _header_key(value: str) -> str:
    text = _norm_header(value)
    for mark in ('"', "׳", "'"):
        text = text.replace(mark, "")
    return " ".join(text.casefold().split())


def normalize_email(value: str) -> str:
    return (value or "").strip().casefold()


def is_valid_email(value: str) -> bool:
    email = normalize_email(value)
    if email.count("@") != 1 or " " in email:
        return False
    local, domain = email.split("@")
    if not local or not domain or "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        return False
    return True


def email_mac(master: bytes, salt: bytes, entry_id: str, email: str) -> bytes:
    message = salt + b"|" + entry_id.encode("utf-8") + b"|" + normalize_email(email).encode("utf-8")
    return hmac.new(master, message, hashlib.sha256).digest()


def _pick_header(indexed: dict[str, str], aliases: frozenset[str]) -> str | None:
    for key, original in indexed.items():
        if key in aliases:
            return original
    return None


def _index_headers(fieldnames: list[str] | None) -> dict[str, str]:
    indexed: dict[str, str] = {}
    for name in fieldnames or []:
        if not name:
            continue
        indexed[_header_key(name)] = name
    return indexed


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
    indexed = _index_headers(reader.fieldnames)
    email_header = _pick_header(indexed, EMAIL_ALIASES)
    given_header = _pick_header(indexed, GIVEN_ALIASES)
    family_header = _pick_header(indexed, FAMILY_ALIASES)
    name_header = _pick_header(indexed, NAME_ALIASES)
    group_header = _pick_header(indexed, GROUP_ALIASES)
    if email_header is None or not ((given_header and family_header) or name_header):
        raise RosterError("roster_headers")
    rows: list[dict] = []
    seen: set[str] = set()
    stats = {"imported": 0, "duplicates": 0, "skipped": 0, "groups": {}}
    for raw in reader:
        if given_header and family_header:
            given = (raw.get(given_header) or "").strip()
            family = (raw.get(family_header) or "").strip()
        else:
            full = (raw.get(name_header) or "").strip()
            parts = full.split(None, 1)
            given = parts[0] if parts else ""
            family = parts[1] if len(parts) > 1 else ""
        email = normalize_email(raw.get(email_header) or "")
        group = (raw.get(group_header) or "").strip() if group_header else ""
        if not given and not family and not email and not group:
            stats["skipped"] += 1
            continue
        if not (given or family) or not is_valid_email(email):
            stats["skipped"] += 1
            continue
        digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
        if digest in seen:
            stats["duplicates"] += 1
            continue
        seen.add(digest)
        rows.append({"given": given, "family": family, "email": email, "group": group})
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
            verifier = email_mac(self.master, salt, entry_id, row["email"])
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

    def verify_email(self, entry_id: str, email: str, ip: str, attempt: str) -> RosterEntry:
        keys = (
            ("entry:" + (entry_id or ""), IDENTITY_LIMITS["entry"]),
            ("ip:" + (ip or "unknown"), IDENTITY_LIMITS["ip"]),
            ("attempt:" + (attempt or "none"), IDENTITY_LIMITS["attempt"]),
        )
        for key, limit in keys:
            if not self.limiter.allow(key, limit, IDENTITY_WINDOW_SECONDS):
                raise RosterError("identity_limited")
        entry = self.entries.get(entry_id or "")
        candidate = normalize_email(email)
        if entry is None or not self._selected(entry) or not is_valid_email(candidate):
            dummy = email_mac(self.master, b"\x00" * 16, "none", "nobody@example.invalid")
            hmac.compare_digest(dummy, b"\x00" * 32)
            ok = False
        else:
            got = email_mac(self.master, entry.salt, entry.id, candidate)
            ok = hmac.compare_digest(got, entry.verifier)
        if not ok:
            for key, _limit in keys:
                self.limiter.add(key, IDENTITY_WINDOW_SECONDS)
            raise RosterError("identity_rejected")
        return entry
