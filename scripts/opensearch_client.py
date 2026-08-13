"""Shared SigV4-signed OpenSearch client builder.

Signs every request from the first call, including against the local
container (OPENSEARCH_ACCESS.md SS5: "the policy is expected to be
tightened" -- one signed code path avoids a silent unsigned shortcut that
only breaks later, and only against the managed domain).
"""

from urllib.parse import urlparse

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection


def build_client(*, url: str, profile: str, region: str) -> OpenSearch:
    """Build an OpenSearch client for `url`, signed with `profile`'s credentials."""

    parsed = urlparse(url)
    host = parsed.hostname
    if host is None:
        raise ValueError(f"OPENSEARCH_URL is missing a host: {url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 9200)

    credentials = boto3.Session(profile_name=profile).get_credentials()
    auth = AWSV4SignerAuth(credentials, region, "es")

    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=auth,
        use_ssl=parsed.scheme == "https",
        verify_certs=parsed.scheme == "https",
        connection_class=RequestsHttpConnection,
    )
