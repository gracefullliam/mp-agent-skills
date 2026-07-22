---
name: cloud-video-production-client
description: Integrate trusted customer servers or local agents with the Firefly Cloud Video Production API. Use when uploading explicitly selected local image/video files, submitting local or URL assets for asynchronous cloud template production, tracking a production by conversation_id, retrieving the final video, handling idempotent retries, receiving signed production webhooks, or diagnosing public API errors from /api/rest/mva/out/cloud endpoints.
---

# Cloud Video Production Client

Integrate with the asynchronous Cloud template-production service. Keep customer credentials outside prompts, source code, logs, and generated documents.

## Load references

- Read `references/api-contract.md` before constructing or interpreting any API request.
- Read `references/webhook-contract.md` when `callback_url` is used or a webhook receiver is implemented.
- Read `references/integration-checklist.md` before integration review, test handoff, or go-live.
- Use `references/openapi.yaml` when a machine-readable contract, SDK generation, or schema validation is needed.

## Resolve connection settings

Require these values from the customer's deployment configuration:

- `base_url`: environment-specific Agent gateway origin; never guess a production URL.
- `api_key`: server-side credential with `produce` scope.
- `callback_secret`: required only when verifying Webhook signatures; obtain it through the agreed secure channel.

Send `X-API-Key` from a server or secret manager. Never place it in browser code or ask the user to paste a real value into chat.
The service operator creates the credential from the database-backed credential control plane and delivers it once through an approved secure channel. Customers do not self-register a key through the public Cloud endpoints; later list operations cannot recover the plaintext.

## Prepare assets

Accept either HTTP/HTTPS media URLs or local files that the current trusted runtime is allowed to read.

For each explicitly selected local file:

1. Resolve the path inside the runtime's approved read scope. Do not scan a home directory, expand an unspecified directory recursively, or upload a file the user did not select.
2. Submit it as multipart field `files` to `POST /api/rest/mva/out/cloud/upload` with the same server-side `X-API-Key`.
3. Require a non-empty `data.files[]` result for every requested file. Stop before `/make` when any item has `url=null` or a non-empty `error`.
4. Map `type` to `asset_type`, `url` to `asset_url`, and `content_sha256` to the same-named production field. Generate a stable request-local `asset_id` without exposing the local absolute path.
5. Merge uploaded descriptors with any caller-provided URL assets, then submit the canonical `assets[]` array to `/make`.

Do not embed local bytes or Base64 in prompts or `/make`. The upload endpoint is not idempotent: an ambiguous upload retry can leave an unused object even though `/make` remains protected by `outer_request_id`.

If the runtime cannot read the user's device—for example, a browser-only or remote cloud agent given only a local path—ask the user to attach the file through the host product or move it into an accessible workspace. Never pretend the path was uploaded.

## Select the workflow

### Create and Poll

Use this as the default integration path.

1. Generate one stable `outer_request_id` for the customer's business operation.
2. Upload explicitly selected local files and normalize all local/URL inputs into canonical `assets[]`.
3. Submit `POST /api/rest/mva/out/cloud/make` with canonical fields only.
4. Persist `conversation_id`, `outer_request_id`, and `request_id` from the response.
5. Poll `POST /api/rest/mva/out/cloud/poll` every 3–5 seconds.
6. Stop on `completed`, `failed`, or `cancelled`.
7. After completion, call `POST /api/rest/mva/out/cloud/queryResult` when the detailed final material or poster is required.

### Create and Webhook

Use this when the customer has a public HTTPS receiver.

1. Register the receiver and signing secret before submitting a task.
2. Include `callback_url`; omit `callback_events` to receive the default terminal events.
3. Verify the signature against the raw request bytes before parsing JSON.
4. Deduplicate deliveries by `event_id` or `X-MP-Video-Delivery`.
5. Return 2xx promptly, then process asynchronously.
6. Use `queryResult` for reconciliation. Do not run continuous Poll merely because a callback was configured; Poll only for recovery or an explicit user action.

## Enforce request rules

- Send flat JSON to make, Poll, and queryResult. Never wrap those bodies in `content`, `BaseRequest`, or another envelope; upload uses multipart instead.
- Use only documented `assets[]` fields such as `asset_id`, `asset_type`, `asset_url`, and `content_sha256`; do not invent aliases.
- Do not send `productId`, `userId`, `project_id`, `conversation_id`, `templateCode`, aspect ratio, high-light timestamps, or template candidates on task creation.
- Treat unknown fields as invalid because the public request models use `extra="forbid"`.
- Provide HTTP/HTTPS asset URLs that the Agent service can access. Only `/out/cloud/upload` accepts multipart; `/make` accepts JSON references and never file bytes.
- Treat `user_intent` as optional text or the documented object. Text is trimmed and truncated to 200 Unicode characters.

## Handle responses

Inspect both HTTP status and body `code`. Branch on `code`, not the `message` text.

- `200`: request succeeded.
- Upload `200` can still contain a failed item. Require every `data.files[]` item to have a non-empty `url` before calling `/make`.
- `409102`: idempotent replay. Adopt the returned existing `conversation_id`; do not create another task.
- `409103` or `409104`: terminal production failure or cancellation; stop waiting.
- `429100`: wait for `Retry-After`, then retry with the same `outer_request_id`.
- For `/make`, handle `503100` or `503101` with bounded exponential backoff and the same `outer_request_id`. Do not apply production idempotency assumptions to upload.
- `400100`, `401100`, `403100`, `404100`, `413100`, `422100`, `422101`: fix the request, upload type/size, credential, task identifier, callback, or asset; do not blind-retry.

Retry network failures and ambiguous submit responses with the same `outer_request_id`. Generate a new `outer_request_id` only for an intentional new production.

## Preserve traceability

Log safe identifiers only:

- environment and request time with timezone
- `X-Request-ID`
- `outer_request_id`
- `conversation_id`
- HTTP status, body `code`, task `status`, and `current_node`
- Webhook `event_id`

Never log API keys, callback secrets, signed asset query strings, raw credentials, or full customer media content.
Never log local absolute paths. A basename may still be sensitive; include it only when the customer's logging policy allows it.

## Produce integration artifacts

When helping a customer implement or review an integration, produce:

- environment and credential placeholders
- request/response field mapping
- idempotency and retry policy
- Poll or Webhook state machine
- webhook verification and deduplication checklist when applicable
- error-code handling table
- smoke-test and launch-readiness checklist

Do not claim production readiness until the customer has passed the checklist in `references/integration-checklist.md`.
