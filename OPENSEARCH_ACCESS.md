# Managed OpenSearch Access

> Korean translation: [OPENSEARCH_ACCESS.ko.md](OPENSEARCH_ACCESS.ko.md)

You do not need this to start. The local container from `docker-compose.yml`
covers normal development, and an index is derived data you can always rebuild.
Read this when you first need the managed domain.

Every value written as `<...>` is delivered through the approved separate
channel. Real account ids, instance ids, and endpoints never go in this
repository.

## 1. Credentials and what they allow

Contributors share **one programmatic IAM user**, resolved by boto3 from the
`AWS_PROFILE` named in `.env`. It is time limited and has no console login.

| Allowed | Denied |
| --- | --- |
| Invoking the approved Bedrock models | RDS, Redis, S3, Secrets Manager, CloudWatch Logs |
| SSM port forwarding through the app EC2 | SSH and every inbound port |
| OpenSearch read/write **on `legal-kit-*` indexes only** | Every other index, infrastructure management, IAM |

The policy boundary was confirmed with the IAM policy simulator on 2026-07-31:

| Path | Signed request |
| --- | --- |
| `legal-kit-*` search, index, delete, per-index `_bulk` | allowed |
| `_cat/indices`, `_cluster/health`, `/` | **implicit deny** |
| Global `_bulk` | **implicit deny** |
| Any index outside `legal-kit-` | **implicit deny** |

This is why `OPENSEARCH_INDEX_PREFIX` is `legal-kit-assessment`. A prefix
outside `legal-kit-` makes every signed request fail, and only on the managed
domain — the local container accepts any name, so the failure surfaces late.

## 2. Working on a shared domain

The credential is shared, so the platform cannot tell contributors apart, and
neither can CloudTrail. Three rules follow, and they are part of the assignment
rather than advice.

**Own one namespace and stay inside it.** Every index you create is
`legal-kit-assessment-<contributor>-...` with the contributor id you were
given. Never read, write, or delete an index carrying someone else's id.

**Never issue a cluster-wide or wildcard-destructive call.** No
`DELETE legal-kit-*`, no global `_bulk`, no cluster settings. The policy already
denies most of these; the ones it does not deny would destroy another
contributor's work with no attribution and no undo.

**Account for your own usage.** Because the credential is shared, AWS billing
and CloudTrail cannot reconstruct which calls were yours. The token, latency,
and cost evidence required by `SUBMISSION.md` can therefore only come from
instrumentation you write yourself, from the first call onward. Nothing can
recover it afterwards.

The Bedrock quota is shared the same way. Cohere Embed v4 is capped at
**300,000 tokens per minute for the whole account**, so a full corpus embedding
run by one contributor consumes what the others also need. Pace your own sends
with a token budget rather than relying on retries — a throttle cannot be
retried away once the minute's budget is spent — and expect throttling when
someone else is indexing.

## 3. Opening the tunnel

The domain sits in a private subnet with no public endpoint and no inbound
port, so it is reachable only through an SSM tunnel via the app EC2.

Prerequisites:

1. AWS CLI v2.
2. **Session Manager plugin.** This is a separate install; the CLI alone fails
   with `SessionManagerPlugin is not found`. Without administrator rights,
   unpacking the portable zip and putting its `bin/` first on `PATH` works.
3. A profile built from the delivered access key:
   `aws configure --profile <profile>` with region `ap-northeast-2`.

Open the tunnel and leave the window open for the session:

```bash
aws ssm start-session --profile <profile> --region ap-northeast-2 \
  --target <app-ec2-instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host=<opensearch-endpoint>,portNumber=443,localPortNumber=443
```

Success prints `Port 443 opened for sessionId ...` and `Waiting for
connections...`. Closing the window ends the session; list and clean up
leftovers with `aws ssm describe-sessions --state Active` and
`aws ssm terminate-session --session-id <id>`.

## 4. Four failures you will hit first

Each of these was reproduced against the staging domain. None of them means the
tunnel is broken.

**Open the local port on 443, not 9200.** SigV4 signs the `Host` header. With
`localPortNumber=9200` the client signs `endpoint:9200` while the server
recomputes over the portless `endpoint`, and you get
`403 The request signature we calculated does not match the signature you
provided`. It is a port mismatch, not a library bug. If 443 is genuinely taken,
sign the portless canonical URL and override the `Host` header instead.

**Do not connect to `localhost`.** The certificate is issued for the endpoint
name, so `https://localhost:443/` fails certificate validation (`curl` exit
60). Do not disable verification — let the client see the real endpoint name:

```bash
curl --resolve <opensearch-endpoint>:443:127.0.0.1 \
     https://<opensearch-endpoint>/legal-kit-assessment-<contributor>/_search
```

In Python, resolve the host to `127.0.0.1` but keep the endpoint name in the
URL, the `Host` header, and TLS verification.

**`GET /` and `_cat/indices` return 403 even when everything works.** They are
outside the policy boundary. Check connectivity with an index path such as
`GET legal-kit-assessment-<contributor>` instead.

**`helpers.bulk()` fails by default.** It calls the global `POST /_bulk`, which
is denied. Pass the index explicitly —
`helpers.bulk(client, actions, index="legal-kit-assessment-...")` — so the
request goes to `legal-kit-*/_bulk`.

## 5. Sign every request from day one

The domain's access policy is currently open enough that an **unsigned request
succeeds** once the tunnel is up. Do not build on that. The policy is expected
to be tightened, and the `legal-kit-*` boundary in section 1 applies only to
signed requests.

An unsigned client passes locally and passes against the staging domain today,
then returns 403 for every call the moment the policy is corrected or the work
is rerun elsewhere. It fails silently and late, which is the failure shape the
development cautions in the README are about. Use SigV4 from the first request.

## 6. Daily development stays local

```powershell
docker compose up -d opensearch
```

An index is derived data. Rebuild it locally as often as you like, keep the
same `legal-kit-assessment-` prefix locally so names transfer unchanged, and
reach for the managed domain only when you need to prove the pipeline works
against it.
