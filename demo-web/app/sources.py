"""Lesson sources and grounded answers.

Default answers are a search over the lecturer's pasted sources. A model is
called only when the lecturer turns that on and a key is already configured.
Roster fields are not part of the prompt.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass


@dataclass
class Source:
    id: str
    title: str
    text: str


def add_source(room, title: str, text: str) -> Source:
    title = (title or "").strip()
    text = (text or "").strip()
    if not title or not text:
        from app.store import StoreError

        raise StoreError("missing_source")
    source = Source(id=secrets.token_hex(4), title=title[:120], text=text[:20000])
    room.sources.append(source)
    return source


def _paragraphs(text: str) -> list[str]:
    parts = [part.strip() for part in text.split("\n")]
    return [part for part in parts if part]


def search_sources(sources: list[Source], question: str, source_ids: list[str] | None) -> dict:
    chosen = sources
    if source_ids:
        wanted = set(source_ids)
        chosen = [source for source in sources if source.id in wanted]
    tokens = [token.casefold() for token in (question or "").split() if len(token) >= 2]
    scored: list[tuple[int, Source, str]] = []
    for source in chosen:
        for paragraph in _paragraphs(source.text):
            folded = paragraph.casefold()
            score = sum(1 for token in tokens if token in folded)
            if score:
                scored.append((score, source, paragraph[:500]))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    snippets = [
        {"source_id": source.id, "title": source.title, "text": paragraph}
        for _score, source, paragraph in scored[:3]
    ]
    if snippets:
        answer = snippets[0]["text"]
    elif not chosen:
        answer = "No source is selected."
    else:
        answer = "Not in the selected sources."
    return {"mode": "source_search", "model": "off", "answer": answer, "snippets": snippets}


def prompt_for_model(sources: list[Source], question: str, source_ids: list[str] | None) -> str:
    chosen = sources
    if source_ids:
        wanted = set(source_ids)
        chosen = [source for source in sources if source.id in wanted]
    blocks = []
    for source in chosen:
        blocks.append(f"Source {source.id} — {source.title}\n{source.text}")
    joined = "\n\n".join(blocks) if blocks else "(no sources)"
    return (
        "Answer only from the sources below. If they do not contain the answer, "
        "say it is not in the sources. Do not invent citations or personal data.\n\n"
        f"{joined}\n\nQuestion: {question.strip()}"
    )
