# Lesson agent

One tool-calling agent supports two tasks: **lesson_summary** relates transcript topics/times to polls, comments, and zone aggregates; **homework_review** reviews one submission and compares it anonymously with peers. Neither task assigns a grade.

The system prompt below is defined in [`app/llm/prompts.py`](../app/llm/prompts.py). The task message adds an index of room/title, poll ids/questions, comment count, homework ids, transcript length, and attention availability. Full text is fetched through tools.

## System prompt

```text
You are the ZooMoodle lesson agent for one class session.
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
```

## Context the tools can see

Built by `Store.snapshot` for one room:

| Field | Content |
| --- | --- |
| Room | Id and title. |
| Transcript | Imported file, after redaction. |
| Polls | Question, options, optional correct option, answers as option + seat zone + pseudonym. |
| Comments | Id, pseudonym, redacted text. |
| Homework | Submission id, pseudonym, redacted text. |
| Attention | Disclaimer, per-zone means, and the raw labeled samples if any. |

Pseudonym: `P-` plus the first 8 hex characters of SHA-256 of the student id. It is stable for the process and it is not the student's name.

Redaction, before the snapshot is built and again on the finished report: whole words of known display names (length at least 3) become `[name]`. Known student ids become that person's pseudonym.

The attendance sheet (names, device ids, confidence) is not in the snapshot.

## Tools

Data tools are read-only. `produce_report` validates and ends the loop; no tool calls another model or writes lesson data.

| Tool | Arguments | Returns |
| --- | --- | --- |
| `get_transcript_segment` | Optional `start_seconds`, `end_seconds`, `keyword` | Matching lines. Timestamps are recognized when a line starts with `mm:ss` or `hh:mm:ss`. Otherwise the text is returned with a note. Capped at 80 lines. |
| `get_poll_results` | `poll_id` or `all`, `by_zone` | Counts, and counts per seat zone. Includes `correct_option` when the lecturer set one. |
| `get_attention_by_zone` | Optional `start_seconds`, `end_seconds` | Zone means, the disclaimer, and `empty` when no samples exist. |
| `list_comments` | none | Id, pseudonym, text. |
| `list_homework_ids` | none | Ids only. |
| `get_homework` | `submission_id` | Pseudonym and text, or an error. |
| `compare_submissions` | `a`, `b` | Word-token Jaccard, token counts, character counts. Computed in Python. |
| `produce_report` | `report` object | Accepts or returns a field error. |

## Loop

1. Messages start with the system prompt and the task.
2. For up to `ZOOMODLE_AGENT_MAX_STEPS` (default 8), call `LLMClient.complete` with the tool schemas.
3. If the model returns no tool call, append a reminder and continue.
4. Data tools run locally. Their JSON is appended as a tool result.
5. `produce_report` before any data tool returns the error "Call at least one data tool before produce_report."
6. A report that fails the schema returns the field error so the model can correct it on a later step.
7. An accepted report is redacted once more and returned to the lecturer or the student. `stub` is false.
8. If the step budget runs out, raise an error. The HTTP layer returns that error. It does not fill in a summary.

There is no second, hidden completion that "cleans up" the answer.

## Output schemas

Lesson summary (`kind` must be `lesson_summary`):

```json
{
  "kind": "lesson_summary",
  "topics": [],
  "zone_findings": [],
  "recommendations": [],
  "missing_data": [],
  "citations": [{ "finding": "", "source": "" }]
}
```

`citations` may be empty only when `missing_data` is not.

Homework review (`kind` must be `homework_review`):

```json
{
  "kind": "homework_review",
  "submission_id": "hw_…",
  "strengths": [],
  "issues": [],
  "comparison": {},
  "not_a_grade": true,
  "citations": []
}
```

`not_a_grade` must be the boolean `true`. Any other value is a tool error.

## Limits and configuration

Redaction covers known names/ids only; an unknown name pasted into homework can remain. Reports request citations, but structural validation does not prove their accuracy. The loop requires a data-tool call, not a complete pedagogical review. The current word tokenizer also needs Hebrew support.

Attention is empty unless labeled samples were loaded. No configured model means HTTP 503 and no provider call. Provider configuration and key storage follow FR-16–18 in the [SRS](04-SRS.md). Save settings before testing if the key is needed for later agent calls; Test alone does not save it. Supported adapters and protocols are listed in [components](06-components.md#llm-adapters).

## Evaluation

Automated with scripted providers and mocked HTTP, without a live key:

- A script that calls `produce_report` first is forced to call a data tool, then a valid summary is accepted.
- A homework report with `not_a_grade: false` is rejected; the corrected report is accepted, and a name the model wrote is scrubbed.
- A model that only returns prose hits the step limit and no report is saved.
- Poll tool output and Jaccard appear in the tool channel the script can see.
- API test: a transcript containing a known name is redacted before the scripted agent runs, and the HTTP body does not contain the name or the API key.

Live evaluation remains open: test tool calling, factual support, citation quality, and report validity on a real transcript and homework. A successful connection test alone does not establish these.
