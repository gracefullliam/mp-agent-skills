---
name: cloud-video-production-client
description: Integrate a customer backend or server-side agent with the Firefly Cloud Video Production public API. Use when creating asynchronous productions from image or video URLs, tracking a task by conversation_id, implementing outer_request_id idempotency, receiving signed Webhooks, retrieving the final video, or troubleshooting documented /out/cloud API errors. Do not use for browser-side API calls, direct file uploads, client-side template selection, or video editing.
---

# Firefly Cloud Video Production Client

Integrate a customer backend or server-side agent with the asynchronous Firefly Cloud Video Production API.

Customers provide only accessible media URLs and a creation intent. The service controls material analysis, highlight detection, template matching, assembly, and rendering.

## Enforce security requirements

- Call all Cloud public APIs from a trusted customer server. Do not call them directly from browser code, mobile applications, or other untrusted clients.
- Send `X-API-Key` only from a server-side secret manager. The key must have `produce` permission.
- Never place an API key or Webhook callback secret in a prompt, source repository, browser bundle, generated document, screenshot, or log.
- Do not embed media binaries in prompts.
- Treat signed or private `asset_url` values as sensitive. Use them only for the API request and do not reproduce them in logs, generated documents, or unrelated responses.
- Treat the API key and Webhook callback secret as separate credentials. Obtain both through the service operator's approved secure delivery channel.

## Resolve connection settings

Use this documented Base URL unless the service operator provides a different environment URL:

```text
https://api-chn.fireflyfusion.cn
```

Use only these public endpoints:

```text
POST /api/rest/mva/out/cloud/make
POST /api/rest/mva/out/cloud/poll
```

The full production-creation URL is:

```text
https://api-chn.fireflyfusion.cn/api/rest/mva/out/cloud/make
```

## Keep identifiers separate

- `X-Request-ID` identifies one HTTP request trace. The caller may provide it as a request Header; the service generates one if omitted. It is not an idempotency key.
- `outer_request_id` identifies one customer business production. The caller provides it in the request Body. Reuse it when retrying the same business operation.
- `conversation_id` identifies the service-side parent task. The service returns it after task creation. Use it to call Poll; do not use it as a request idempotency key.
- Webhook `event_id` identifies one generated business event. Retries of the same event reuse the same `event_id`.

Generate and persist one stable `outer_request_id` before the first submission. Generate a new value only when the customer intentionally starts a new production.

## Create a production

Send a flat JSON Body to:

```http
POST /api/rest/mva/out/cloud/make
Content-Type: application/json
X-API-Key: <server-side-api-key>
X-Request-ID: customer-trace-001
```

Example Body:

```json
{
  "user_intent": "生成一条节奏明快的宠物日常短片",
  "assets": [
    {
      "asset_type": "video",
      "asset_url": "https://cdn.example.com/media/pet-001.mp4"
    }
  ],
  "outer_request_id": "customer-order-20260720-001"
}
```

Use only these documented top-level fields:

- `user_intent`
- `assets`
- `outer_request_id`
- `callback_url`
- `callback_events`

Do not wrap the Body in `content`, `BaseRequest`, `data`, or another envelope.

### Normalize user_intent

- Treat `user_intent` as an optional string.
- The service removes leading and trailing whitespace.
- The service keeps at most the first 200 Unicode characters.

### Validate assets

- Require `assets` to contain at least one item. The maximum number may vary by environment.
- Permit only `asset_type` and `asset_url` in each item.
- Do not require or send `asset_id`, `duration_sec`, highlight timestamps, media labels, template information, or other undocumented fields.
- Require `asset_type` to be `image` or `video` and to match the media type recognizable from the URL and response content.
- Require `asset_url` to be an HTTP or HTTPS URL reachable from the service Agent environment.
- Do not use multipart file upload.

The service validates DNS resolution, network access, HTTP status, response content, and media type before creating a task. If validation returns code `422101`, no `conversation_id` was created and production did not start.

### Configure callbacks

- Treat `callback_url` as optional and require an allowed public HTTPS URL when present.
- Permit `callback_events` only when `callback_url` is present.
- If `callback_url` is present and `callback_events` is omitted, subscribe only to `production.completed`, `production.failed`, and `production.cancelled`.

Do not send undocumented fields such as `productId`, `userId`, `conversation_id`, `templateCode`, aspect ratio, highlight timestamps, candidate templates, or client-side template-matching results. The public request model rejects unknown fields.

## Persist the creation response

After a successful request, persist:

- `conversation_id`
- `request_id`
- `outer_request_id`
- task status

Example:

```json
{
  "code": 200,
  "data": {
    "conversation_id": "43a6df89-c48d-4a71-9a71-95013a4109b5",
    "status": "queued",
    "request_id": "customer-trace-001",
    "outer_request_id": "customer-order-20260720-001"
  },
  "message": "successful",
  "success": true
}
```

## Handle idempotent submissions

- `409102`: adopt the returned original `conversation_id` and continue tracking it, even when `success=false`.
- `409101`: reuse the `callback_url` and `callback_events` from the first request.
- `409100`: confirm the intended operation. Generate a new ID only when the customer explicitly wants a new production.

After a network failure, timeout, or ambiguous submission response, retry with the same `outer_request_id`. Never create a new `outer_request_id` merely because the first response was not received.

## Use Poll mode

Use Poll when `callback_url` is absent. Send this request every 3–5 seconds:

```http
POST /api/rest/mva/out/cloud/poll
Content-Type: application/json
X-API-Key: <server-side-api-key>
```

```json
{
  "conversation_id": "43a6df89-c48d-4a71-9a71-95013a4109b5"
}
```

Read these response fields when present:

- `status`
- `current_node`
- `current_node_description`
- `error_messages`
- `video_url`

Apply these rules:

- Display `current_node_description` as the user-facing progress message.
- Use `current_node` only for technical logging and troubleshooting. Do not display it directly to ordinary users.
- Do not build long-term business logic from `current_node` or `current_node_description`; the service may change node names or configured descriptions.
- Stop Poll when `status` becomes `completed`, `failed`, or `cancelled`.
- Treat a non-empty `video_url` as the playable final result.
- If the task is completed but `video_url` is null or empty, stop regular Poll, do not store it as playable, retain `conversation_id`, and perform controlled reconciliation or service-side investigation.

## Use Webhook mode

Use Webhook when the customer operates a public HTTPS receiver. To subscribe to every currently supported event, provide:

```json
{
  "callback_url": "https://customer.example.com/webhooks/video-production",
  "callback_events": [
    "input.validated",
    "intent.completed",
    "highlight.completed",
    "material_analysis.completed",
    "template_match.completed",
    "render.submitted",
    "production.completed",
    "production.failed",
    "production.cancelled"
  ]
}
```

Do not continuously Poll when Webhook is configured. Use `/poll` only when:

- a callback may have been lost;
- the persisted state is uncertain;
- a completed event contains no usable `video_url`;
- the user explicitly requests a refresh or reconciliation.

## Verify Webhook requests

Verify each delivery before parsing JSON:

1. Read the unmodified raw HTTP request Body as bytes.
2. Read `X-MP-Video-Timestamp`.
3. Reject timestamps outside the agreed window; use five minutes unless another window was agreed.
4. Construct the signed content as `<timestamp>.<raw_request_body>`.
5. Compute HMAC-SHA256 using the callback secret.
6. Remove the `sha256=` prefix from `X-MP-Video-Signature`.
7. Compare the expected and supplied hexadecimal digests using a constant-time comparison.
8. Parse JSON only after signature verification succeeds.
9. Require `X-MP-Video-Event` to equal Body `event`.
10. Require `X-MP-Video-Delivery` to equal Body `event_id`.

Do not parse and reserialize the Body before verification. Changes to whitespace, key order, or Unicode escaping change the signature.

```python
import hashlib
import hmac
import time


def verify_webhook(
    secret: str,
    timestamp: str,
    raw_body: bytes,
    signature: str,
) -> bool:
    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        return False

    if abs(int(time.time()) - timestamp_value) > 300:
        return False

    signed_content = timestamp.encode("utf-8") + b"." + raw_body
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_content,
        hashlib.sha256,
    ).hexdigest()

    supplied = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, supplied)
```

## Process Webhook events

Branch on Body `event`. Do not branch on `current_node`, `current_node_description`, or translated display text.

Supported intermediate events:

- `input.validated`
- `intent.completed`
- `highlight.completed`
- `material_analysis.completed`
- `template_match.completed`
- `render.submitted`

Supported terminal events:

- `production.completed`
- `production.failed`
- `production.cancelled`

Intermediate event `data` is currently empty and does not expose internal analysis results. `production.completed` may contain:

```json
{
  "data": {
    "video_url": "https://result.example.com/test/final.mp4"
  }
}
```

`data.video_url` may be a string or null. When `status=completed` but `video_url` is null, treat the task as terminal, stop normal waiting, do not store the result as playable, retain `conversation_id`, and use `/poll` for controlled reconciliation or contact the service operator.

Webhook payloads do not currently expose customer `outer_request_id`, tenant ID, application ID, original asset URLs, media labels, highlight ranges, template codes, candidate rankings, rendering task IDs, or detailed internal error stacks. Use `conversation_id` to reconcile the latest public task state.

## Acknowledge and deduplicate Webhooks

For a valid Webhook:

1. Persist `event_id` and the verified Body reliably.
2. Deduplicate by `event_id`.
3. Return a 2xx response promptly.
4. Perform slower business processing asynchronously.

If the same `event_id` is delivered again, do not repeat business side effects, but still return 2xx. Non-2xx responses, connection failures, and timeouts may trigger delivery retries. A Webhook delivery failure does not change the production task to failed.

## Handle API errors

Inspect both the HTTP status and response Body `code`. Branch on `code`; do not parse `message` text.

| Code | Meaning and action |
| --- | --- |
| `400100` | Request validation failed. Fix JSON syntax, field names, required fields, or unknown fields using `data.errors[]`. |
| `401100` | Authentication failed. Supply or rotate the API key. |
| `403100` | The credential lacks `produce` permission. |
| `404100` | Task not found. Verify environment, tenant, and `conversation_id`. |
| `409100` | `outer_request_id` conflicts with a different production request. |
| `409101` | Callback configuration differs from the original idempotent request. |
| `409102` | Idempotent replay. Adopt the returned original task. |
| `409103` | Production failed. Stop waiting and retain safe identifiers and public error information. |
| `409104` | Production cancelled. Stop waiting. |
| `413100` | Too many assets. Reduce the asset list. |
| `422100` | Invalid callback URL. Use an allowed public HTTPS URL. |
| `422101` | One or more assets are unavailable. Correct entries identified in `data.errors[]`. |
| `429100` | Honor `Retry-After` and retry with the same `outer_request_id`. |
| `500100` | Internal service error. Retry only when the operation remains idempotent. |
| `503100` | Callback-related service unavailable. Use Poll when appropriate or retry later with the same identifiers. |
| `503101` | Dependent service unavailable. Use bounded exponential backoff and the same `outer_request_id`. |

Do not blindly retry malformed requests, authentication failures, permission failures, invalid callback configuration, invalid assets, or unknown tasks. For retryable errors, use bounded exponential backoff and preserve all trace identifiers.

## Preserve traceability

Customer-side technical logs may include only:

- environment
- request time with timezone
- `X-Request-ID`
- `outer_request_id`
- `conversation_id`
- HTTP status
- response Body `code`
- task status
- `current_node`
- Webhook event and `event_id`

Never log API keys, callback secrets, authorization or credential Headers, Webhook signatures, raw customer media, complete private or signed asset URLs, or internal error stacks not returned by the public API.

## Verify before go-live

- Confirm the correct production Base URL.
- Store the API key and callback secret in a server-side secret manager.
- Verify that no browser or mobile client sends `X-API-Key`.
- Persist `outer_request_id`, `conversation_id`, and `request_id`.
- Verify that Poll stops at `completed`, `failed`, and `cancelled`.
- Treat `409102` as adoption of the original task.
- Reuse the same `outer_request_id` after a timeout or uncertain submission.
- Verify that invalid assets fail before task creation.
- Verify raw-Body signature validation and timestamp rejection.
- Verify `event_id` deduplication and prompt 2xx acknowledgment.
- Test one image, one video, mixed media, invalid media, idempotent replay, conflicting replay, unknown task, duplicate Webhook delivery, invalid signature, expired timestamp, and `video_url=null`.
