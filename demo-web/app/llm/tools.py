"""Read-only tools. Outputs use pseudonyms and redacted text, never names."""

from __future__ import annotations

import hashlib
import json
import re

from app.llm.providers import ToolSpec

SUMMARY_KEYS = ("kind", "topics", "zone_findings", "recommendations", "missing_data", "citations")
HOMEWORK_KEYS = ("kind", "submission_id", "strengths", "issues", "comparison", "not_a_grade", "citations")


def pseudonym(student_id: str) -> str:
    return "P-" + hashlib.sha256(student_id.encode("utf-8")).hexdigest()[:8]


def redact(text: str, names: list[str], student_ids: list[str]) -> str:
    output = text or ""
    for name in sorted({item.strip() for item in names if item and len(item.strip()) >= 3}, key=len, reverse=True):
        output = re.sub(rf"\b{re.escape(name)}\b", "[name]", output, flags=re.IGNORECASE)
    for student_id in student_ids:
        if len(student_id) >= 3:
            output = re.sub(rf"\b{re.escape(student_id)}\b", pseudonym(student_id), output)
    return output


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def jaccard(left: str, right: str) -> float:
    a = _word_set(left)
    b = _word_set(right)
    if not a and not b:
        return 1.0
    return round(len(a & b) / len(a | b), 3)


class ToolRegistry:
    def __init__(self, snapshot: dict):
        self.snapshot = snapshot
        self.accepted: dict | None = None

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                "get_transcript_segment",
                "Return transcript lines. Optional start_seconds, end_seconds, and keyword. Times work only if lines start with mm:ss or hh:mm:ss.",
                {
                    "type": "object",
                    "properties": {
                        "start_seconds": {"type": "number"},
                        "end_seconds": {"type": "number"},
                        "keyword": {"type": "string"},
                    },
                },
            ),
            ToolSpec(
                "get_poll_results",
                "Poll counts. Pass poll_id or 'all'. by_zone groups answers by seat zone. Includes correct_option when the lecturer set one.",
                {
                    "type": "object",
                    "properties": {
                        "poll_id": {"type": "string"},
                        "by_zone": {"type": "boolean"},
                    },
                    "required": ["poll_id"],
                },
            ),
            ToolSpec(
                "get_attention_by_zone",
                "Anonymous attention aggregates by seat zone. Optional start_seconds and end_seconds. Empty means the camera path was not run.",
                {
                    "type": "object",
                    "properties": {
                        "start_seconds": {"type": "number"},
                        "end_seconds": {"type": "number"},
                    },
                },
            ),
            ToolSpec(
                "list_comments",
                "Anonymized comments and suggestions for this room.",
                {"type": "object", "properties": {}},
            ),
            ToolSpec(
                "list_homework_ids",
                "Ids of homework submissions. No names and no bodies.",
                {"type": "object", "properties": {}},
            ),
            ToolSpec(
                "get_homework",
                "One submission's text, keyed by submission_id. The author is a pseudonym.",
                {
                    "type": "object",
                    "properties": {"submission_id": {"type": "string"}},
                    "required": ["submission_id"],
                },
            ),
            ToolSpec(
                "compare_submissions",
                "Word-token Jaccard similarity and lengths for two submission ids. Does not call a model.",
                {
                    "type": "object",
                    "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
                    "required": ["a", "b"],
                },
            ),
            ToolSpec(
                "produce_report",
                "Finish the task with a JSON report. Lesson summary keys: kind, topics, zone_findings, recommendations, missing_data, citations. Homework keys: kind, submission_id, strengths, issues, comparison, not_a_grade, citations.",
                {"type": "object", "properties": {"report": {"type": "object"}}, "required": ["report"]},
            ),
        ]

    def dispatch(self, name: str, arguments: dict, task: str) -> tuple[bool, dict]:
        arguments = arguments or {}
        if name == "produce_report":
            report = arguments.get("report", arguments)
            return self._produce(report, task)
        handler = {
            "get_transcript_segment": self._transcript,
            "get_poll_results": self._polls,
            "get_attention_by_zone": self._attention,
            "list_comments": self._comments,
            "list_homework_ids": self._homework_ids,
            "get_homework": self._homework,
            "compare_submissions": self._compare,
        }.get(name)
        if handler is None:
            return False, {"error": f"Unknown tool {name}."}
        return False, handler(arguments)

    def _transcript(self, arguments: dict) -> dict:
        text = self.snapshot.get("transcript") or ""
        if not text.strip():
            return {"empty": True, "note": "No transcript was imported.", "lines": []}
        lines = text.splitlines()
        keyword = (arguments.get("keyword") or "").strip().lower()
        start = arguments.get("start_seconds")
        end = arguments.get("end_seconds")
        timed = []
        has_time = False
        for line in lines:
            stamp = _leading_timestamp(line)
            if stamp is not None:
                has_time = True
            if stamp is not None and start is not None and stamp < float(start):
                continue
            if stamp is not None and end is not None and stamp > float(end):
                continue
            if keyword and keyword not in line.lower():
                continue
            timed.append(line)
        chosen = timed if (has_time or keyword) else lines
        truncated = len(chosen) > 80
        return {
            "empty": not chosen,
            "timestamps": has_time,
            "truncated": truncated,
            "lines": chosen[:80],
        }

    def _polls(self, arguments: dict) -> dict:
        wanted = str(arguments.get("poll_id") or "all")
        by_zone = arguments.get("by_zone", True)
        polls = self.snapshot.get("polls") or []
        if wanted not in ("all", "*", ""):
            polls = [poll for poll in polls if poll["id"] == wanted]
        if not polls:
            return {"empty": True, "polls": [], "note": "No matching poll."}
        rendered = []
        for poll in polls:
            counts: dict[str, int] = {option: 0 for option in poll["options"]}
            zones: dict[str, dict[str, int]] = {}
            for answer in poll["answers"]:
                option = answer["option"]
                counts[option] = counts.get(option, 0) + 1
                zone = zones.setdefault(answer["seat_zone"], {})
                zone[option] = zone.get(option, 0) + 1
            item = {
                "id": poll["id"],
                "question": poll["question"],
                "options": poll["options"],
                "correct_option": poll.get("correct_option"),
                "counts": counts,
                "answer_count": len(poll["answers"]),
            }
            if by_zone:
                item["by_zone"] = zones
            rendered.append(item)
        return {"empty": False, "polls": rendered}

    def _attention(self, arguments: dict) -> dict:
        attention = self.snapshot.get("attention") or {}
        # The snapshot is already aggregated for the whole lesson. A time filter
        # is applied when the snapshot carries raw samples.
        samples = attention.get("samples") or []
        if not samples:
            return {
                "empty": attention.get("empty", True),
                "disclaimer": attention.get("disclaimer", ""),
                "zones": attention.get("zones") or {},
                "source": attention.get("source", "none"),
            }
        start = arguments.get("start_seconds")
        end = arguments.get("end_seconds")
        chosen = []
        for sample in samples:
            if start is not None and sample["t_seconds"] < float(start):
                continue
            if end is not None and sample["t_seconds"] > float(end):
                continue
            chosen.append(sample)
        buckets: dict[str, list[float]] = {}
        for sample in chosen:
            buckets.setdefault(sample["zone"], []).append(sample["level"])
        zones = {
            zone: {"mean_level": round(sum(values) / len(values), 3), "samples": len(values)}
            for zone, values in sorted(buckets.items())
        }
        return {
            "empty": not chosen,
            "disclaimer": attention.get("disclaimer", ""),
            "source": "sample-not-camera" if chosen else "none",
            "zones": zones,
        }

    def _comments(self, _arguments: dict) -> dict:
        comments = self.snapshot.get("comments") or []
        return {
            "empty": not comments,
            "comments": [
                {"id": item["id"], "author": item["pseudonym"], "text": item["text"]}
                for item in comments
            ],
        }

    def _homework_ids(self, _arguments: dict) -> dict:
        items = self.snapshot.get("homework") or []
        return {"empty": not items, "ids": [item["id"] for item in items]}

    def _homework(self, arguments: dict) -> dict:
        wanted = arguments.get("submission_id")
        for item in self.snapshot.get("homework") or []:
            if item["id"] == wanted:
                return {
                    "id": item["id"],
                    "author": item["pseudonym"],
                    "text": item["text"],
                }
        return {"error": "Unknown submission_id."}

    def _compare(self, arguments: dict) -> dict:
        found = {item["id"]: item for item in self.snapshot.get("homework") or []}
        left = found.get(arguments.get("a"))
        right = found.get(arguments.get("b"))
        if left is None or right is None:
            return {"error": "Both submission ids must exist."}
        return {
            "a": left["id"],
            "b": right["id"],
            "jaccard": jaccard(left["text"], right["text"]),
            "tokens_a": len(_word_set(left["text"])),
            "tokens_b": len(_word_set(right["text"])),
            "chars_a": len(left["text"]),
            "chars_b": len(right["text"]),
        }

    def _produce(self, report: dict, task: str) -> tuple[bool, dict]:
        if not isinstance(report, dict):
            return False, {"error": "report must be an object."}
        if task == "lesson_summary":
            if report.get("kind") != "lesson_summary":
                return False, {"error": "kind must be lesson_summary."}
            for key in SUMMARY_KEYS:
                if key not in report:
                    return False, {"error": f"Missing field {key}."}
            if not isinstance(report["citations"], list) or not isinstance(report["missing_data"], list):
                return False, {"error": "citations and missing_data must be lists."}
            if not report["citations"] and not report["missing_data"]:
                return False, {"error": "Add citations or explain missing_data."}
        elif task == "homework_review":
            if report.get("kind") != "homework_review":
                return False, {"error": "kind must be homework_review."}
            for key in HOMEWORK_KEYS:
                if key not in report:
                    return False, {"error": f"Missing field {key}."}
            if report.get("not_a_grade") is not True:
                return False, {"error": "Set not_a_grade to true. This agent does not grade."}
            if not isinstance(report["citations"], list):
                return False, {"error": "citations must be a list."}
        else:
            return False, {"error": "Unknown task."}
        self.accepted = report
        return True, {"accepted": True}


def scrub_report(report: dict, names: list[str], student_ids: list[str]) -> dict:
    encoded = json.dumps(report, ensure_ascii=False)
    return json.loads(redact(encoded, names, student_ids))


_TIME = re.compile(r"^\s*[\[(]?(\d{1,2}):(\d{2})(?::(\d{2}))?")


def _leading_timestamp(line: str) -> float | None:
    match = _TIME.match(line)
    if not match:
        return None
    first, second, third = match.groups()
    if third is None:
        return int(first) * 60 + int(second)
    return int(first) * 3600 + int(second) * 60 + int(third)
