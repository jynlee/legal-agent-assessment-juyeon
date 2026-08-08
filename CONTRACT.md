# Portable Application-Service Contract

The required boundary is defined by the Pydantic models and protocol in
`src/legal_agent_assessment/contracts.py`.

```python
class GeneralLegalAgent(Protocol):
    async def answer(
        self,
        request: GeneralLegalRequest,
    ) -> GeneralLegalResponse:
        ...
```

The service is:

- single-turn: one independent question per call;
- stateless: no conversational memory is required between calls;
- database-free at the public boundary;
- async and suitable for timeout/cancellation by its caller;
- typed and JSON-serializable;
- independent of Peitho, FastAPI, ORM, DI, and `ITool`;
- backed by replaceable OpenSearch and Bedrock adapters.

The response distinguishes these states:

- `answered`: answer text is grounded by one or more returned citations;
- `insufficient_evidence`: supplied evidence cannot support an answer;
- `out_of_scope`: the question is outside the supported legal coverage;
- `dependency_unavailable`: a required external dependency failed.

`answered` requires citations. Non-answered states must not fabricate answer text
or sources. Every response exposes the dataset, index, embedding, generation
model, and prompt versions used. Internal retrieval diagnostics may be returned
separately from consumer-safe text.

You may add internal fields and models, but do not silently change the public
contract. Propose a contract change with a compatibility explanation when the
boundary cannot represent a necessary behavior.

