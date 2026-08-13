"""Retrieval test-set leakage check: lexical overlap between a question and
its source chunk.

Implements reports/decisions/2026-08-13-retrieval-evaluation-design.md
Decision 5's automated overlap check. Pure: no I/O. A character-bigram
overlap ratio is used rather than a word-tokenized measure because no
Korean tokenizer is assumed available offline (the same constraint
embedding.estimate_tokens documents) and Korean's agglutinative morphology
makes naive whitespace-splitting an unreliable word boundary anyway --
character bigrams need no tokenizer and are stable across particle
attachment.
"""


def lexical_overlap_ratio(question: str, source_text: str) -> float:
    """Fraction of `question`'s character bigrams that also appear in `source_text`.

    1.0 means every 2-character sequence in the question also occurs
    somewhere in the source chunk (near-total lexical overlap -- a strong
    signal the question is a light rewording rather than a genuine
    paraphrase). 0.0 means no bigram overlap at all. A question shorter
    than 2 characters has no bigrams and returns 0.0 rather than dividing
    by zero.
    """

    if len(question) < 2:
        return 0.0

    question_bigrams = {question[i : i + 2] for i in range(len(question) - 1)}
    source_bigrams = {source_text[i : i + 2] for i in range(len(source_text) - 1)}
    return len(question_bigrams & source_bigrams) / len(question_bigrams)


__all__ = ["lexical_overlap_ratio"]
