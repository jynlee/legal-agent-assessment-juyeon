"""One real Bedrock Cohere Embed v4 call; print the raw response shape.

    uv run python scripts/smoke_bedrock_embedding.py

Run this once before trusting scripts/bedrock_embedding.py's response
parsing. If the printed shape doesn't match what
legal_agent_assessment.embedding.parse_embed_response expects, fix that
function first -- this script is the ground truth, not the assumption.
"""

import json
import os

import boto3

from legal_agent_assessment.embedding import build_embed_request


def main() -> None:
    """Call the configured embedding model once and print the raw response."""

    region = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "ap-northeast-2"))
    model_id = os.environ.get("EMBEDDING_MODEL_ID", "global.cohere.embed-v4:0")

    client = boto3.client("bedrock-runtime", region_name=region)
    request = build_embed_request(["약사법 제1조 목적 조항"], input_type="search_document")

    response = client.invoke_model(modelId=model_id, body=json.dumps(request))
    body = json.loads(response["body"].read())

    print(f"model: {model_id}")
    print(f"top-level keys: {sorted(body.keys())}")
    print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])


if __name__ == "__main__":
    main()
