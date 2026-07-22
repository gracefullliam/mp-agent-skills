# Customer integration checklist

## Contract setup

- [ ] Confirm the target environment and obtain its `base_url` from the service owner.
- [ ] Store the production API key with `produce` scope as `FIREFLY_MVA_PROD_API_KEY` in a server-side secret manager.
- [ ] Do not configure fallback to `FIREFLY_MVA_QA_API_KEY`, `API_KEY`, `X_API_KEY`, or another environment credential.
- [ ] Keep API keys and callback secrets out of browser code, repositories, screenshots, and tickets.
- [ ] Use exactly the four `/api/rest/mva/out/cloud/*` paths documented by this Skill.
- [ ] Send flat JSON without a `content` wrapper.

## Request construction

- [ ] Generate and persist a stable `outer_request_id` before the first submit attempt.
- [ ] Use `/out/cloud/upload` only from a trusted runtime with access to explicitly selected local files.
- [ ] Keep API keys out of browser/mobile clients, prompts, command output, and repositories.
- [ ] Send local files as repeated multipart field `files`; let the HTTP client set the boundary.
- [ ] Require every upload item to have a non-empty `url`; do not call `/make` after a partial upload failure.
- [ ] Map upload `type/url/content_sha256` to `asset_type/asset_url/content_sha256` without exposing absolute local paths.
- [ ] Use only canonical field names; do not implement alias fallback.
- [ ] Ensure every `asset_url` is reachable from the Agent environment.
- [ ] Set `asset_type` explicitly and consistently with the media.
- [ ] Supply realistic video duration and dimensions when known.
- [ ] Do not send template, highlight, aspect-ratio, product, or internal project fields.
- [ ] Treat user-intent text after 200 Unicode characters as truncated by the service.

## Async state handling

- [ ] Persist `conversation_id`, `outer_request_id`, and `request_id` together.
- [ ] Model at least `queued`, `running`, `completed`, `failed`, and `cancelled`.
- [ ] Display `current_node_description`; do not expose internal node keys as customer copy.
- [ ] Poll every 3–5 seconds only when Poll mode is selected.
- [ ] Stop Poll on all terminal states.
- [ ] Call `queryResult` for final material reconciliation or poster retrieval.
- [ ] Treat `409102` as an accepted existing task, despite `success=false`.

## Retry and recovery

- [ ] Retry ambiguous network failures with the same `outer_request_id`.
- [ ] Honor `Retry-After` for `429100`.
- [ ] Use bounded exponential backoff for retryable `500100`/`503xxx` failures.
- [ ] Do not blind-retry validation, authentication, permission, asset, or not-found errors.
- [ ] Generate a new `outer_request_id` only for an intentional new production.
- [ ] Provide an operator action to query a known `conversation_id` without resubmitting.
- [ ] Do not assume upload is idempotent; record and clean up unused objects after ambiguous upload retries.

## Webhook, when enabled

- [ ] Use a public HTTPS callback URL.
- [ ] Verify HMAC-SHA256 against the raw body.
- [ ] Validate timestamp freshness with an agreed clock-skew window.
- [ ] Deduplicate `event_id` using durable storage.
- [ ] Return 2xx after durable acceptance and process asynchronously.
- [ ] Tolerate duplicates and out-of-order delivery.
- [ ] Use `queryResult` for reconciliation rather than continuous Poll.

## Smoke tests

- [ ] Upload one local image through `/out/cloud/upload`, submit the returned URL, and reach `completed`.
- [ ] Upload one local video through `/out/cloud/upload`, submit the returned URL, and reach `completed`.
- [ ] Mix one uploaded local file with one caller-provided URL in the same production.
- [ ] Reject an unsupported extension, empty file, oversized file, oversized batch, and exhausted tenant quota.
- [ ] Simulate one per-file storage failure and verify `/make` is not called.
- [ ] Submit one valid image and reach `completed` with non-empty `video_url`.
- [ ] Submit one valid video and reach `completed`.
- [ ] Submit mixed image/video assets.
- [ ] Replay the same `outer_request_id` and receive `409102` with the same `conversation_id`.
- [ ] Submit an unreachable asset and receive `422101` without a task ID.
- [ ] Submit an unknown field and receive `400100` with `data.errors[]`.
- [ ] Query an unknown task and receive `404100`.
- [ ] Trigger or simulate rate limiting and honor `Retry-After`.
- [ ] When Webhook is enabled, verify signature rejection, duplicate delivery, and terminal reconciliation.

## Support handoff

Capture these non-secret values in an issue:

```text
environment:
request_time_with_timezone:
X-Request-ID:
outer_request_id:
conversation_id:
HTTP_status:
response_code:
task_status:
current_node:
callback_enabled:
webhook_event_id:
asset_count_and_types:
```
