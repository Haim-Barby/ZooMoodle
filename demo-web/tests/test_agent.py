import json

from app.llm.agent import AgentError, LessonAgent
from app.llm.providers import LLMClient, LLMResponse, ToolCall
from app.llm.tools import pseudonym, redact


class Scripted:
    def __init__(self, steps):
        self.steps = list(steps)
        self.seen = []

    def complete(self, messages, tools, max_tokens=1200):
        self.seen.append(messages)
        if not self.steps:
            return LLMResponse(text="", tool_calls=[], model="script")
        return self.steps.pop(0)


def _summary():
    return {
        "kind": "lesson_summary",
        "topics": [{"title": "HMAC", "time_range": "00:02", "note": "Introduced tokens"}],
        "zone_findings": [{"zone": "back-right", "observation": "More wrong answers"}],
        "recommendations": ["Revisit HMAC next time."],
        "missing_data": [],
        "citations": [{"finding": "back-right missed the poll", "source": "poll:p1"}],
    }


def _snapshot():
    return {
        "room_id": "abc",
        "title": "Lesson",
        "transcript": "00:02 HMAC keeps a token honest.\n",
        "polls": [{
            "id": "p1",
            "question": "What does HMAC give us?",
            "options": ["Integrity", "Compression"],
            "correct_option": "Integrity",
            "answers": [
                {"option": "Compression", "seat_zone": "back-right", "pseudonym": "P-aaaaaaaa"},
            ],
        }],
        "comments": [],
        "homework": [
            {"id": "hw_a", "pseudonym": "P-aaaaaaaa", "text": "HMAC is a keyed hash."},
            {"id": "hw_b", "pseudonym": "P-bbbbbbbb", "text": "A hash is not the same as HMAC."},
        ],
        "attention": {
            "empty": False,
            "disclaimer": "stub",
            "source": "sample-not-camera",
            "zones": {},
            "samples": [{"t_seconds": 120, "zone": "back-right", "level": 0.2, "source": "sample-not-camera"}],
        },
    }


def test_summary_agent_must_call_a_tool_then_report():
    script = Scripted([
        LLMResponse(text="", tool_calls=[ToolCall("1", "produce_report", {"report": _summary()})], model="script"),
        LLMResponse(text="", tool_calls=[ToolCall("2", "get_poll_results", {"poll_id": "p1", "by_zone": True})], model="script"),
        LLMResponse(text="", tool_calls=[ToolCall("3", "produce_report", {"report": _summary()})], model="script"),
    ])
    report = LessonAgent(LLMClient(script), max_steps=4).run("lesson_summary", _snapshot())
    assert report["kind"] == "lesson_summary"
    assert report["citations"][0]["source"] == "poll:p1"
    # The premature produce_report was rejected, so the model had to read data.
    tool_payloads = [message.content for message in script.seen[-1] if message.role == "tool"]
    assert any("Call at least one data tool" in item for item in tool_payloads)
    assert any("back-right" in item for item in tool_payloads)


def test_homework_review_requires_not_a_grade_and_hides_names():
    review = {
        "kind": "homework_review",
        "submission_id": "hw_a",
        "strengths": ["States that HMAC is keyed."],
        "issues": [],
        "comparison": {"peer": "hw_b", "note": "Similar topic."},
        "not_a_grade": False,
        "citations": [{"finding": "definition", "source": "homework:hw_a"}],
    }
    fixed = dict(review, not_a_grade=True)
    script = Scripted([
        LLMResponse(text="", tool_calls=[
            ToolCall("1", "get_homework", {"submission_id": "hw_a"}),
            ToolCall("2", "compare_submissions", {"a": "hw_a", "b": "hw_b"}),
        ], model="script"),
        LLMResponse(text="", tool_calls=[ToolCall("3", "produce_report", {"report": review})], model="script"),
        LLMResponse(text="", tool_calls=[ToolCall("4", "produce_report", {"report": fixed})], model="script"),
    ])
    named = dict(fixed, strengths=["Ada Lovelace wrote a clear line."])
    script.steps[-1] = LLMResponse(text="", tool_calls=[ToolCall("4", "produce_report", {"report": named})], model="script")
    report = LessonAgent(LLMClient(script), max_steps=5).run(
        "homework_review",
        _snapshot(),
        submission_id="hw_a",
        audience="student",
        names=["Ada Lovelace"],
        student_ids=["stu-99"],
    )
    assert report["not_a_grade"] is True
    assert "Ada Lovelace" not in json.dumps(report)
    assert "[name]" in json.dumps(report)
    blob = json.dumps([message.content for batch in script.seen for message in batch if message.role == "tool"])
    assert "jaccard" in blob


def test_agent_stops_without_inventing_a_report():
    script = Scripted([LLMResponse(text="I will guess the class was fine.", tool_calls=[], model="script")])
    try:
        LessonAgent(LLMClient(script), max_steps=2).run("lesson_summary", _snapshot())
        raise AssertionError("should stop")
    except AgentError as exc:
        assert "without a valid report" in exc.message


def test_redaction_helpers():
    assert pseudonym("stu-99").startswith("P-")
    cleaned = redact("Ada Lovelace wrote stu-99.", ["Ada Lovelace"], ["stu-99"])
    assert "Ada" not in cleaned
    assert "stu-99" not in cleaned
    assert "[name]" in cleaned
