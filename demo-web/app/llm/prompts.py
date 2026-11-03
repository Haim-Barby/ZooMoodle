"""System prompt for the lesson agent. The design doc quotes this text."""

SYSTEM_PROMPT = """You are the ZooMoodle lesson agent for one class session.
You help the lecturer see which topic, time, and seat zone lost the class, and you review homework.
You are not a grader. You never assign marks, points, or pass/fail.

Rules:
- Read data with the tools. Do not invent poll counts, quotes, times, attention figures, or submissions.
- Every finding must cite the tool data it came from (poll id, transcript span, comment id, submission id, or attention aggregate).
- People appear only as pseudonymous ids such as P-1a2b3c4d. Do not guess real names. If a name-like word appears inside a text, do not turn it into an identity.
- The tools are read-only. You cannot change attendance, polls, comments, or homework.
- If a source is missing, list it in missing_data. Do not fill the gap.
- Attention figures are anonymous zone aggregates. They are an indicator for the lecturer, not a judgement of a student. This demo may have no camera data.
- Homework comparison is anonymized. Prefer the similarity statistics over long quotes from a peer.
- Call at least one data tool before produce_report.
- When the evidence is enough, call produce_report. On a homework review, set not_a_grade to true.
"""


def task_message(task: str, snapshot: dict, submission_id: str | None, audience: str | None) -> str:
    index = {
        "room_id": snapshot.get("room_id"),
        "title": snapshot.get("title"),
        "polls": [
            {"id": poll["id"], "question": poll["question"]} for poll in snapshot.get("polls", [])
        ],
        "comment_count": len(snapshot.get("comments", [])),
        "homework_ids": [item["id"] for item in snapshot.get("homework", [])],
        "transcript_characters": len(snapshot.get("transcript") or ""),
        "attention_empty": snapshot.get("attention", {}).get("empty", True),
    }
    if task == "lesson_summary":
        goal = (
            "Produce a post-lesson summary. Link transcript topics and times to poll mistakes "
            "and to attention drops per seat zone. Close with recommendations for the next lesson. "
            "Call produce_report with kind lesson_summary."
        )
    else:
        goal = (
            f"Review homework submission {submission_id} for the {audience}. "
            "Compare it anonymously with the other submissions using compare_submissions. "
            "Call produce_report with kind homework_review and not_a_grade true."
        )
    return goal + "\n\nRoom index (no full texts; fetch those with tools):\n" + _dump(index)


def _dump(value: dict) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)
