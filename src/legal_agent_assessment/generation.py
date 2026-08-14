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

First, decide whether this question is even a legal question relevant to \
the domains this assistant covers. If the question is not a legal question \
at all (small talk, unrelated business or personal advice, a question about \
this assistant itself), or is a legal question about a domain this \
assistant does not cover, respond with status "out_of_scope" and no answer \
text -- regardless of what the sources above happen to contain.

Otherwise, if, and only if, the sources above do not actually contain \
enough information to answer this specific question, respond with status \
"insufficient_evidence" and no answer text. Otherwise, respond with status \
"answered", an answer grounded strictly in the sources, and the chunk_id of \
every source you relied on.

Respond with exactly one JSON object and no other text, in this shape:
{{"status": "answered" | "insufficient_evidence" | "out_of_scope", "answer": \
string or null, "cited_chunk_ids": [string, ...]}}"""

# Bumped whenever _PROMPT_TEMPLATE changes, and recorded in
# `RuntimeVersions.prompt` so a stored answer names the prompt that produced
# it. Kept next to the template so the two cannot silently desync.
PROMPT_VERSION = "prompt-v2"


def build_answer_prompt(question: str, citations: Sequence[Citation]) -> str:
    """Build the Claude prompt for one grounded-answer attempt.

    Every candidate citation is shown with its `chunk_id` as a citable
    label, so a response's `cited_chunk_ids` can be matched back to the
    exact `Citation` objects retrieval already built -- no re-fetching or
    re-parsing citation content from the model's own answer text.
    """

    # Retrieved chunk text is interpolated verbatim, with no delimiter
    # escaping: a chunk containing "[some-id]" or its own instruction-like
    # text is not neutralized. Accepted as a low-risk surface here -- the
    # corpus is the fixed, delivered Korean statute/judgement dataset, not
    # user-supplied content -- and `agent.py` independently discards any
    # cited_chunk_id it did not itself retrieve.
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


def _strip_code_fence(raw_text: str) -> str:
    """Unwrap a markdown-fenced payload, if the model wrapped one.

    Returning JSON inside ```` ```json ... ``` ```` is a very common real
    model output pattern even when the prompt asks for bare JSON, and it is
    not a malformed answer -- only a differently packaged one. Text without
    a leading fence is returned unchanged (stripped).
    """

    stripped = raw_text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    # Drop the opening fence line, which may carry a language tag ("```json").
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


def _parse_cited_chunk_ids(value: object) -> tuple[str, ...]:
    """Read `cited_chunk_ids` from an untrusted parsed body.

    A missing key, an explicit `null`, or any non-list value all mean "no
    citations" rather than an error. Non-string elements are dropped: in
    this codebase a real chunk_id is always a string, so a number or a
    nested object can never match a retrieved id anyway, and dropping it
    matches how `agent.py` already discards ids it did not retrieve.
    """

    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def parse_answer_response(raw_text: str) -> ParsedAnswer:
    """Parse Claude's JSON answer, enforcing contracts.py's grounding invariant.

    `GeneralLegalResponse.validate_grounding_state` (contracts.py) raises
    `ValueError` if a non-ANSWERED response carries an `answer` or
    `citations`. The raw model response is never trusted to already respect
    this: whenever the parsed `status` is anything other than the literal
    string `"answered"` -- including `"out_of_scope"`, a status the model
    invented, or an "insufficient_evidence"/"out_of_scope" response that
    still filled in `answer`/`cited_chunk_ids` -- both fields are cleared
    here, unconditionally, before this function returns.

    Three recognized status strings map to their matching `AnswerStatus`:
    `"answered"`, `"out_of_scope"`. Everything else -- the literal string
    `"insufficient_evidence"`, an unrecognized status the model invented, a
    missing `status` key -- maps to `AnswerStatus.INSUFFICIENT_EVIDENCE`,
    the conservative default this module has always used for "anything not
    explicitly recognized as something else."

    Shape is validated too, not just syntax: valid JSON that is not an
    object (`[]`, `null`, a bare number or string) raises `ValueError`, the
    same failure the caller already handles for undecodable text, rather
    than an `AttributeError` from calling `.get()` on it.
    """

    try:
        parsed = json.loads(_strip_code_fence(raw_text))
    except json.JSONDecodeError as error:
        raise ValueError(f"could not parse model response as JSON: {raw_text!r}") from error

    if not isinstance(parsed, dict):
        raise ValueError(f"could not parse model response as JSON: {raw_text!r}")

    status = parsed.get("status")

    if status == "answered":
        return ParsedAnswer(
            status=AnswerStatus.ANSWERED,
            answer=parsed.get("answer"),
            cited_chunk_ids=_parse_cited_chunk_ids(parsed.get("cited_chunk_ids")),
        )

    if status == "out_of_scope":
        return ParsedAnswer(status=AnswerStatus.OUT_OF_SCOPE, answer=None, cited_chunk_ids=())

    return ParsedAnswer(status=AnswerStatus.INSUFFICIENT_EVIDENCE, answer=None, cited_chunk_ids=())


__all__ = ["PROMPT_VERSION", "ParsedAnswer", "build_answer_prompt", "parse_answer_response"]
