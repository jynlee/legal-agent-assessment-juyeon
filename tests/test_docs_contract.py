"""Keep the bilingual document set and the agent entry points from drifting."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]

# English source -> Korean translation. English is authoritative everywhere.
TRANSLATED_DOCS = {
    "README.en.md": "README.md",
    "ASSIGNMENT.md": "ASSIGNMENT.ko.md",
    "DATASET.md": "DATASET.ko.md",
    "CONTRACT.md": "CONTRACT.ko.md",
    "SUBMISSION.md": "SUBMISSION.ko.md",
}


@pytest.mark.parametrize(("source", "translation"), sorted(TRANSLATED_DOCS.items()))
def test_every_english_document_has_a_non_empty_korean_translation(
    source: str,
    translation: str,
) -> None:
    for name in (source, translation):
        path = ROOT / name
        assert path.is_file(), f"{name} is missing"
        assert path.read_text(encoding="utf-8").strip(), f"{name} is empty"


@pytest.mark.parametrize("translation", sorted(TRANSLATED_DOCS.values()))
def test_every_translation_states_that_english_is_authoritative(translation: str) -> None:
    """A reader must never mistake a translation for the governing text."""

    content = (ROOT / translation).read_text(encoding="utf-8")

    assert "정본" in content, f"{translation} does not name its authoritative source"


def test_claude_md_points_at_agents_md_instead_of_copying_it() -> None:
    """One copy of the rules, so Claude Code and Codex cannot diverge."""

    content = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "AGENTS.md" in content
    assert len(content.splitlines()) < 20, "CLAUDE.md should stay a pointer, not a copy"
