"""Stable, Peitho-independent application-service boundary."""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """Strict JSON-serializable base for public assessment contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AnswerStatus(StrEnum):
    """Outcome of one independent General Legal Agent call."""

    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUT_OF_SCOPE = "out_of_scope"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"


class GeneralLegalRequest(ContractModel):
    """One stateless owner question."""

    request_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=10_000)


class Citation(ContractModel):
    """Verifiable identity and minimal excerpt for one supporting source."""

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_uri: str | None = None
    official_number: str | None = None
    locator: str | None = None
    excerpt: str = Field(min_length=1, max_length=2_000)


class RetrievalHit(ContractModel):
    """Optional diagnostic hit kept separate from consumer-safe answer text."""

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float


class RuntimeVersions(ContractModel):
    """Frozen versions necessary to reproduce one answer."""

    dataset: str = Field(min_length=1)
    normalization: str = Field(min_length=1)
    chunking: str = Field(min_length=1)
    index: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    generation_model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    rerank: str = Field(min_length=1)


class GeneralLegalResponse(ContractModel):
    """Grounded answer or explicit non-answer for one request."""

    request_id: str = Field(min_length=1, max_length=128)
    status: AnswerStatus
    answer: str | None = None
    citations: tuple[Citation, ...] = ()
    retrieval_hits: tuple[RetrievalHit, ...] = ()
    limitations: tuple[str, ...] = ()
    versions: RuntimeVersions

    @model_validator(mode="after")
    def validate_grounding_state(self) -> "GeneralLegalResponse":
        """Require grounded text only for an answered result."""

        if self.status is AnswerStatus.ANSWERED:
            if not self.answer or not self.answer.strip():
                raise ValueError("answered responses require answer text")
            if not self.citations:
                raise ValueError("answered responses require at least one citation")
        elif self.answer is not None or self.citations:
            raise ValueError("non-answered responses cannot contain answer text or citations")
        return self


class GeneralLegalAgent(Protocol):
    """Portable single-turn, stateless application service."""

    async def answer(self, request: GeneralLegalRequest) -> GeneralLegalResponse:
        """Answer one independent question without Peitho runtime objects."""

        ...
