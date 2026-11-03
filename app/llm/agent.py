"""Tool-calling loop. Stops on an accepted produce_report or at max steps."""

from __future__ import annotations

import json

from app.llm.prompts import SYSTEM_PROMPT, task_message
from app.llm.providers import ChatMessage, LLMClient
from app.llm.tools import ToolRegistry, scrub_report


class AgentError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class LessonAgent:
    def __init__(self, client: LLMClient, max_steps: int = 8):
        self.client = client
        self.max_steps = max_steps

    def run(
        self,
        task: str,
        snapshot: dict,
        submission_id: str | None = None,
        audience: str | None = None,
        names: list[str] | None = None,
        student_ids: list[str] | None = None,
    ) -> dict:
        registry = ToolRegistry(snapshot)
        messages = [
            ChatMessage("system", SYSTEM_PROMPT),
            ChatMessage("user", task_message(task, snapshot, submission_id, audience)),
        ]
        saw_data = False
        for _step in range(self.max_steps):
            result = self.client.complete(messages, registry.specs())
            if not result.tool_calls:
                messages.append(ChatMessage("assistant", result.text or ""))
                messages.append(
                    ChatMessage(
                        "user",
                        "Call a data tool if you have not, then call produce_report with the JSON report.",
                    )
                )
                continue
            messages.append(ChatMessage("assistant", result.text or "", tool_calls=result.tool_calls))
            for call in result.tool_calls:
                if call.name == "produce_report" and not saw_data:
                    payload = {"error": "Call at least one data tool before produce_report."}
                    done = False
                else:
                    done, payload = registry.dispatch(call.name, call.arguments, task)
                    if call.name != "produce_report":
                        saw_data = True
                messages.append(
                    ChatMessage(
                        "tool",
                        json.dumps(payload, ensure_ascii=False),
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
                if done and registry.accepted is not None:
                    return scrub_report(registry.accepted, names or [], student_ids or [])
        raise AgentError(
            f"The agent stopped after {self.max_steps} steps without a valid report. No partial report is returned."
        )


class SummaryService:
    def __init__(self, client_factory, max_steps: int):
        self._client_factory = client_factory
        self._max_steps = max_steps

    def summarize(self, snapshot: dict, names: list[str], student_ids: list[str]) -> dict:
        agent = LessonAgent(self._client_factory(), self._max_steps)
        report = agent.run("lesson_summary", snapshot, names=names, student_ids=student_ids)
        return {"kind": "lesson_summary", "report": report, "stub": False}


class HomeworkReviewService:
    def __init__(self, client_factory, max_steps: int):
        self._client_factory = client_factory
        self._max_steps = max_steps

    def review(
        self,
        snapshot: dict,
        submission_id: str,
        audience: str,
        names: list[str],
        student_ids: list[str],
    ) -> dict:
        if audience not in ("student", "lecturer"):
            raise AgentError("audience must be student or lecturer.")
        agent = LessonAgent(self._client_factory(), self._max_steps)
        report = agent.run(
            "homework_review",
            snapshot,
            submission_id=submission_id,
            audience=audience,
            names=names,
            student_ids=student_ids,
        )
        return {"kind": "homework_review", "report": report, "stub": False}
