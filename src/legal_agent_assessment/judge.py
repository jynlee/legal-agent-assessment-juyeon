"""LLM-judge for generation-evaluation grounding: builds a judge prompt and
parses Claude's classification of whether an answer is actually supported
by its own cited excerpts.

Implements reports/decisions/2026-08-14-generation-evaluation-design.md
Decision 2: the same fixed Sonnet 4.6 model judges every `answered`
response, not a second model identity. Pure: no boto3, no network,
matching AGENTS.md's I/O separation -- scripts/evaluate_generation.py is
the network-facing caller. This is evaluation-only tooling, not part of
the GeneralLegalAgent contract itself, which is why it is a separate
module from generation.py rather than added to it.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from legal_agent_assessment.contracts import Citation

GroundingVerdict = Literal["grounded", "partially_grounded", "unsupported"]

# Bumped whenever _JUDGE_PROMPT_TEMPLATE changes. Kept next to the template
# so the two cannot silently desync -- same convention as
# generation.PROMPT_VERSION, but this is evaluation-only tooling and is
# never threaded into RuntimeVersions (RuntimeVersions describes what
# produced a real GeneralLegalResponse; the judge is not part of that
# response's production, only of evaluating it afterward).
JUDGE_PROMPT_VERSION = "judge-prompt-v2"

_JUDGE_PROMPT_TEMPLATE = """You are auditing another AI system's answer to \
a Korean legal question, checking only whether the answer is actually \
supported by the source excerpts it cited -- not whether the answer is a \
good answer, not whether the sources themselves are correct law.

Question: {question}

Answer given: {answer}

Cited sources (the ONLY evidence the answer is allowed to rely on):
{sources}

Classify the answer:
- "grounded": every factual claim in the answer is directly supported by \
the cited sources.
- "partially_grounded": some claims are supported by the cited sources, \
but at least one claim is not directly traceable to them.
- "unsupported": the answer makes claims the cited sources do not \
support, or draws a conclusion the sources do not actually reach.

Do not show your work. Do not list or number the individual claims you \
checked. Do not write any text before or after the JSON object -- your \
entire response must be the JSON object itself and nothing else. Keep \
"justification" to one short sentence.

Respond with exactly one JSON object in this shape:
{{"grounding": "grounded" | "partially_grounded" | "unsupported", \
"justification": string}}"""


def build_judge_prompt(question: str, answer: str, citations: Sequence[Citation]) -> str:
    """Build the judge prompt for one already-generated answer.

    Citations are shown with their chunk_id as a label (matching
    generation.build_answer_prompt's own convention) purely for the
    judge's own readability -- unlike the main generation prompt, nothing
    here needs the judge to cite a chunk_id back, only to compare prose
    against evidence.
    """

    sources = "\n\n".join(
        f"[{citation.chunk_id}] {citation.title}\n{citation.excerpt}" for citation in citations
    )
    return _JUDGE_PROMPT_TEMPLATE.format(question=question, answer=answer, sources=sources)


@dataclass(frozen=True, slots=True)
class ParsedVerdict:
    """One parsed, validator-safe judge outcome."""

    grounding: GroundingVerdict
    justification: str


def _strip_code_fence(raw_text: str) -> str:
    """Unwrap a markdown-fenced payload, if the model wrapped one.

    Same shape as generation._strip_code_fence -- duplicated rather than
    imported, since it is a small, self-contained helper and this module
    stays independent of generation.py's own private internals, per this
    project's one-file-one-responsibility convention.
    """

    stripped = raw_text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


_VALID_VERDICTS = {"grounded", "partially_grounded", "unsupported"}


def parse_judge_response(raw_text: str) -> ParsedVerdict:
    """Parse Claude's judge JSON response.

    Shape is validated, not just syntax: valid JSON that is not an object,
    or an object whose `grounding` value is not one of the three
    recognized strings, raises `ValueError` -- an unrecognized verdict is
    surfaced as an error, never silently treated as any particular
    classification.
    """

    try:
        parsed = json.loads(_strip_code_fence(raw_text))
    except json.JSONDecodeError as error:
        raise ValueError(f"could not parse judge response as JSON: {raw_text!r}") from error

    if not isinstance(parsed, dict):
        raise ValueError(f"could not parse judge response as JSON: {raw_text!r}")

    grounding = parsed.get("grounding")
    if not isinstance(grounding, str) or grounding not in _VALID_VERDICTS:
        raise ValueError(f"judge returned an unrecognized grounding value: {grounding!r}")

    justification = parsed.get("justification")
    if not isinstance(justification, str):
        justification = ""

    return ParsedVerdict(grounding=cast(GroundingVerdict, grounding), justification=justification)


__all__ = [
    "JUDGE_PROMPT_VERSION",
    "GroundingVerdict",
    "ParsedVerdict",
    "build_judge_prompt",
    "parse_judge_response",
]
