"""Feature 5: students submit homework, the LLM reviews it and compares it
anonymously with the other submissions. The provider is a fake that follows
the real tool-calling loop (list -> get -> compare -> produce_report)."""

from app.llm.providers import LLMResponse, ToolCall
from app.llm.tools import jaccard
from tests.conftest import HOME_IP, check_in_class, join, make_client, open_room, signed

SECRET_KEY = "sk-test-SECRET-review-0123456789"
DANA = "פרספטרון מחשב סכום משוקלל של הקלטים ומפעיל פונקציית סף. דנה לוי כתבה את זה."
YOSSI = "פרספטרון מחשב סכום משוקלל ומפעיל פונקציית סף, ואז מעדכן משקלות לפי השגיאה."


class ReviewProvider:
    seen_messages = []
    seen_keys = []

    def __init__(self, config):
        ReviewProvider.seen_keys.append(config.api_key)
        self.calls = 0
        self.ids = []
        self.target = None

    def complete(self, messages, tools, max_tokens=1200):
        ReviewProvider.seen_messages.append(list(messages))
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(text="", tool_calls=[ToolCall("1", "list_homework_ids", {})], model="fake")
        if self.calls == 2:
            import json

            self.ids = json.loads(messages[-1].content)["ids"]
            self.target = next(i for i in self.ids if i in messages[1].content)
            return LLMResponse(text="", tool_calls=[ToolCall("2", "get_homework", {"submission_id": self.target})], model="fake")
        if self.calls == 3:
            other = next(i for i in self.ids if i != self.target)
            return LLMResponse(text="", tool_calls=[ToolCall("3", "compare_submissions", {"a": self.target, "b": other})], model="fake")
        report = {
            "kind": "homework_review",
            "submission_id": self.target,
            "strengths": ["הגדרה נכונה של סכום משוקלל"],
            "issues": ["חסר הסבר על עדכון המשקלות"],
            "comparison": ["דומה בחלקה לעבודה אחרת (Jaccard מתוך הכלי)"],
            "not_a_grade": True,
            "citations": [self.target],
        }
        return LLMResponse(text="", tool_calls=[ToolCall("4", "produce_report", {"report": report})], model="fake")

    def test_connection(self):
        raise NotImplementedError


def _room_with_two_submissions(app, client):
    room_id, headers = open_room(client)
    dana = check_in_class(app, client, room_id, "דנה לוי")
    yossi = join(client, room_id, "יוסי כהן", "remote", ip=HOME_IP).json()
    a = signed(client, dana, "POST", f"/api/rooms/{room_id}/submissions", {"text": DANA, "filename": "hw1.md"})
    assert a.status_code == 200, a.text
    b = signed(client, yossi, "POST", f"/api/rooms/{room_id}/submissions", {"text": YOSSI})
    return room_id, headers, dana, yossi, a.json()["id"], b.json()["id"]


def test_students_submit_and_the_lecturer_sees_the_list():
    app, client = make_client()
    room_id, headers, dana, _yossi, sub_a, _sub_b = _room_with_two_submissions(app, client)
    listed = client.get(f"/api/rooms/{room_id}/submissions", headers=headers).json()["submissions"]
    assert {s["name"] for s in listed} == {"דנה לוי", "יוסי כהן"}
    # A student sees only their own submission; a new one replaces the old one.
    again = signed(client, dana, "POST", f"/api/rooms/{room_id}/submissions", {"text": "גרסה 2"}).json()
    mine = signed(client, dana, "GET", f"/api/rooms/{room_id}/submissions").json()["submissions"]
    assert [s["id"] for s in mine] == [again["id"]] and again["id"] != sub_a
    assert signed(client, dana, "POST", f"/api/rooms/{room_id}/submissions", {"text": "  "}).status_code == 400


def test_lecturer_review_compares_anonymously_and_drops_the_key():
    app, client = make_client()
    app.state.provider_factory = ReviewProvider
    ReviewProvider.seen_messages = []
    room_id, headers, _dana, _yossi, sub_a, _sub_b = _room_with_two_submissions(app, client)
    made = client.post(
        f"/api/rooms/{room_id}/submissions/{sub_a}/review",
        json={"provider": "openai", "model": "gpt-4o-mini", "api_key": SECRET_KEY},
        headers=headers,
    )
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["audience"] == "lecturer"
    assert "חוזקות" in body["text"] and "זו ביקורת ולא ציון." in body["text"]
    # The model never saw a real name: only pseudonyms and "[name]".
    sent = "\n".join(m.content or "" for msgs in ReviewProvider.seen_messages for m in msgs)
    assert "דנה לוי" not in sent and "יוסי כהן" not in sent and "[name]" in sent
    assert '"jaccard"' in sent
    assert SECRET_KEY not in made.text and ReviewProvider.seen_keys[-1] == SECRET_KEY
    room = app.state.store.get(room_id)
    assert SECRET_KEY not in repr(vars(room))


def test_student_reviews_only_their_own_submission():
    app, client = make_client()
    app.state.provider_factory = ReviewProvider
    room_id, _headers, dana, _yossi, sub_a, sub_b = _room_with_two_submissions(app, client)
    llm = {"provider": "openai", "model": "m", "api_key": SECRET_KEY}
    own = signed(client, dana, "POST", f"/api/rooms/{room_id}/submissions/{sub_a}/review", llm)
    assert own.status_code == 200 and own.json()["audience"] == "student"
    other = signed(client, dana, "POST", f"/api/rooms/{room_id}/submissions/{sub_b}/review", llm)
    assert other.status_code == 403
    missing = signed(client, dana, "POST", f"/api/rooms/{room_id}/submissions/{sub_a}/review", {"provider": "openai", "model": "m"})
    assert missing.status_code == 400 and missing.json()["error"] == "missing_key"


def test_review_needs_another_submission_to_compare():
    app, client = make_client()
    room_id, headers = open_room(client)
    dana = check_in_class(app, client, room_id, "דנה לוי")
    sub = signed(client, dana, "POST", f"/api/rooms/{room_id}/submissions", {"text": DANA}).json()["id"]
    alone = client.post(f"/api/rooms/{room_id}/submissions/{sub}/review", json={"provider": "openai", "model": "m", "api_key": "k"}, headers=headers)
    assert alone.status_code == 409 and alone.json()["error"] == "need_two_submissions_to_compare"


def test_similarity_counts_hebrew_words():
    assert jaccard("סכום משוקלל", "סכום משוקלל") == 1.0
    assert jaccard("סכום משוקלל", "פונקציית סף") == 0.0
    assert 0 < jaccard(DANA, YOSSI) < 1
