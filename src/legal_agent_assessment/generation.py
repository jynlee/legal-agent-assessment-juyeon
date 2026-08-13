"""Answer-generation prompt construction and validator-safe response parsing.

Implements the generation-layer half of
reports/decisions/2026-08-13-retrieval-design.md Decision 4: retrieval only
enforces a mechanical zero-hit floor, every other insufficient_evidence
determination is delegated to this prompt and parsed back here. Pure: no
boto3, no network, matching AGENTS.md's I/O separation.
src/legal_agent_assessment/agent.py is the network-facing caller.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from legal_agent_assessment.contracts import AnswerStatus, Citation

_PROMPT_TEMPLATE = """You are a Korean legal research assistant. Answer the \
question below using ONLY the source excerpts provided. Do not use any \
outside knowledge, and do not guess or extrapolate beyond what the sources \
say.

Question: {question}

Sources:
{sources}

If, and only if, the sources above do not actually contain enough \
information to answer this specific question, respond with status \
"insufficient_evidence" and no answer text. Otherwise, respond with status \
"answered", an answer grounded strictly in the sources, and the chunk_id of \
every source you relied on.

Respond with exactly one JSON object and no other text, in this shape:
{{"status": "answered" | "insufficient_evidence", "answer": string or null, \
"cited_chunk_ids": [string, ...]}}"""


def build_answer_prompt(question: str, citations: Sequence[Citation]) -> str:
    """Build the Claude prompt for one grounded-answer attempt.

    Every candidate citation is shown with its `chunk_id` as a citable
    label, so a response's `cited_chunk_ids` can be matched back to the
    exact `Citation` objects retrieval already built -- no re-fetching or
    re-parsing citation content from the model's own answer text.
    """

    sources = "\n\n".join(
        f"[{citation.chunk_id}] {citation.title}\n{citation.excerpt}" for citation in citations
    )
    return _PROMPT_TEMPLATE.format(question=question, sources=sources)


@dataclass(frozen=True, slots=True)
class ParsedAnswer:
    """One parsed, validator-safe generation outcome."""

    status: AnswerStatus
    answer: str | None
    cited_chunk_ids: tuple[str, ...]


def parse_answer_response(raw_text: str) -> ParsedAnswer:
    """Parse Claude's JSON answer, enforcing contracts.py's grounding invariant.

    `GeneralLegalResponse.validate_grounding_state` (contracts.py) raises
    `ValueError` if a non-ANSWERED response carries an `answer` or
    `citations`. The raw model response is never trusted to already respect
    this: whenever the parsed `status` is anything other than the literal
    string `"answered"` -- including a status the model invented, or an
    "insufficient_evidence" response that still filled in `answer`/
    `cited_chunk_ids` -- both fields are cleared here, unconditionally,
    before this function returns.
    """

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"could not parse model response as JSON: {raw_text!r}") from error

    if parsed.get("status") == "answered":
        return ParsedAnswer(
            status=AnswerStatus.ANSWERED,
            answer=parsed.get("answer"),
            cited_chunk_ids=tuple(parsed.get("cited_chunk_ids", [])),
        )

    return ParsedAnswer(status=AnswerStatus.INSUFFICIENT_EVIDENCE, answer=None, cited_chunk_ids=())


__all__ = ["ParsedAnswer", "build_answer_prompt", "parse_answer_response"]
