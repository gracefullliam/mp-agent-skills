#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "cos-python-sdk-v5>=1.9.37,<2",
#   "requests>=2.31,<3",
# ]
# ///
"""Upload explicitly selected local media to COS and create a cloud production."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sys
import time
from typing import Any
import uuid

import requests


API_PREFIX = "/api/rest/mva/out/cloud"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
PROFILE = {
    "environment": "production",
    "api_key_env": "FIREFLY_MVA_PROD_API_KEY",
    "base_url": "https://mp-video-agent.fireflyfusion.cn",
    "id_prefix": "prod-local-media",
}


class WorkflowError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload selected local images/videos directly to COS and create a cloud video task."
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        dest="inputs",
        metavar="PATH",
        help="Explicitly selected local image or video; repeat for mixed inputs.",
    )
    parser.add_argument("--intent", help="Production intent sent as user_intent; required unless validating only.")
    parser.add_argument(
        "--outer-request-id",
        help="Stable idempotency identifier. A profile-prefixed value is generated when omitted.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll to a terminal state and return the final video URL without downloading it.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=4.0,
        help="Poll interval in seconds, from 3 through 5 (default: 4).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate and hash inputs without credentials, uploads, or API requests.",
    )
    return parser.parse_args()


def resolve_profile() -> dict[str, Any]:
    skill_name = Path(__file__).resolve().parents[1].name
    if skill_name != "cloud-video-production-client":
        raise WorkflowError(f"unsupported Skill directory: {skill_name}")
    return PROFILE


def resolve_inputs(values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise WorkflowError("one or more selected inputs do not exist or are not regular files")
        paths.append(path)
    return paths


def media_type(path: Path) -> tuple[str, str]:
    content_type = mimetypes.guess_type(path.name)[0]
    if content_type is None:
        raise WorkflowError("an input has an unrecognized media extension")
    if content_type.startswith("image/"):
        return content_type, "image"
    if content_type.startswith("video/"):
        return content_type, "video"
    raise WorkflowError("every input must be an image or video")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_local_inputs(paths: list[Path]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for index, path in enumerate(paths, start=1):
        content_type, asset_type = media_type(path)
        size = path.stat().st_size
        if size <= 0:
            raise WorkflowError(f"input[{index}] is empty")
        prepared.append(
            {
                "path": path,
                "filename": path.name,
                "size": size,
                "content_type": content_type,
                "asset_type": asset_type,
                "content_sha256": sha256_file(path),
            }
        )
        print(f"input[{index}]: type={asset_type}, size={size}, sha256=verified", flush=True)
    return prepared


def new_request_id(profile: dict[str, Any], operation: str) -> str:
    return f"{profile['id_prefix']}-{operation}-{uuid.uuid4().hex}"


def sanitized_errors(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("errors"), list):
        return []
    allowed = {"field", "reason", "asset_id", "http_status"}
    return [
        {key: value for key, value in item.items() if key in allowed}
        for item in data["errors"]
        if isinstance(item, dict)
    ]


def api_post(
    session: requests.Session,
    base_url: str,
    api_key: str,
    profile: dict[str, Any],
    endpoint: str,
    payload: dict[str, Any],
    timeout: float = 60,
) -> tuple[int, dict[str, Any], str, str | None]:
    operation = endpoint.strip("/").replace("/", "-")
    trace_id = new_request_id(profile, operation)
    response = session.post(
        f"{base_url}{API_PREFIX}{endpoint}",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "X-Request-ID": trace_id,
        },
        timeout=timeout,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise WorkflowError(f"{endpoint} returned non-JSON HTTP {response.status_code}") from exc
    return response.status_code, body, trace_id, response.headers.get("Retry-After")


def require_success(endpoint: str, status: int, body: dict[str, Any]) -> dict[str, Any]:
    if status < 200 or status >= 300 or body.get("code") != 200 or not body.get("success"):
        raise WorkflowError(
            f"{endpoint} failed: HTTP={status}, code={body.get('code')}, "
            f"errors={sanitized_errors(body)}"
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise WorkflowError(f"{endpoint} returned no data object")
    return data


def sdk_upload(init_data: dict[str, Any], item: dict[str, Any]) -> None:
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as exc:
        raise WorkflowError("Tencent COS SDK is missing; run this file with `uv run --script`") from exc

    credentials = init_data.get("credentials")
    required_headers = init_data.get("required_headers")
    if not isinstance(credentials, dict) or not isinstance(required_headers, dict):
        raise WorkflowError("/upload/init returned incomplete COS control data")

    metadata: dict[str, str] = {}
    upload_kwargs: dict[str, Any] = {}
    for name, value in required_headers.items():
        lower_name = name.lower()
        if lower_name == "content-type":
            upload_kwargs["ContentType"] = value
        elif lower_name.startswith("x-cos-meta-"):
            metadata[name] = value
        else:
            raise WorkflowError(f"unsupported required COS header: {name}")
    if metadata:
        upload_kwargs["Metadata"] = metadata

    try:
        config = CosConfig(
            Region=init_data["region"],
            SecretId=credentials["tmp_secret_id"],
            SecretKey=credentials["tmp_secret_key"],
            Token=credentials["session_token"],
        )
        client = CosS3Client(config)
        client.upload_file(
            Bucket=init_data["bucket"],
            Key=init_data["object_key"],
            LocalFilePath=str(item["path"]),
            PartSize=int(init_data.get("part_size_mb", 16)),
            MAXThread=5,
            EnableMD5=False,
            **upload_kwargs,
        )
    finally:
        credentials.clear()
        init_data.pop("credentials", None)


def upload_item(
    session: requests.Session,
    base_url: str,
    api_key: str,
    profile: dict[str, Any],
    item: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    status, body, trace_id, _ = api_post(
        session,
        base_url,
        api_key,
        profile,
        "/upload/init",
        {
            "filename": item["filename"],
            "size": item["size"],
            "content_type": item["content_type"],
            "content_sha256": item["content_sha256"],
        },
    )
    init_data = require_success("/upload/init", status, body)
    upload_id = init_data.get("upload_id")
    if not isinstance(upload_id, str) or not upload_id:
        raise WorkflowError("/upload/init returned no upload_id")
    print(
        f"upload/init[{index}]: request_id={trace_id}, HTTP={status}, code={body.get('code')}",
        flush=True,
    )

    sdk_upload(init_data, item)
    print(f"cos/upload[{index}]: completed", flush=True)

    for attempt in range(1, 4):
        try:
            status, body, trace_id, retry_after = api_post(
                session,
                base_url,
                api_key,
                profile,
                "/upload/complete",
                {"upload_id": upload_id},
            )
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt - 1))
            continue
        if body.get("code") not in (500100, 503101) or attempt == 3:
            break
        delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt - 1)
        time.sleep(min(delay, 30))
    complete_data = require_success("/upload/complete", status, body)
    files = complete_data.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise WorkflowError(f"/upload/complete returned no descriptor for input[{index}]")
    descriptor = files[0]
    if not descriptor.get("url") or descriptor.get("error"):
        raise WorkflowError(f"/upload/complete returned an unusable descriptor for input[{index}]")
    descriptor_type = descriptor.get("type")
    if descriptor_type not in {"image", "video"}:
        raise WorkflowError(f"/upload/complete returned an invalid media type for input[{index}]")
    print(
        f"upload/complete[{index}]: request_id={trace_id}, HTTP={status}, code={body.get('code')}",
        flush=True,
    )
    return {
        "asset_id": f"{profile['id_prefix']}-asset-{index:03d}",
        "asset_type": descriptor_type,
        "asset_url": descriptor["url"],
        "content_sha256": descriptor.get("content_sha256") or item["content_sha256"],
    }


def create_task(
    session: requests.Session,
    base_url: str,
    api_key: str,
    profile: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            status, body, trace_id, retry_after = api_post(
                session, base_url, api_key, profile, "/make", payload, timeout=120
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(2 ** (attempt - 1))
            continue
        code = body.get("code")
        if code in (200, 409102):
            data = body.get("data")
            if not isinstance(data, dict) or not data.get("conversation_id"):
                raise WorkflowError("/make returned no conversation_id")
            print(
                f"make: request_id={trace_id}, HTTP={status}, code={code}, status={data.get('status')}",
                flush=True,
            )
            return data, trace_id
        if code not in (429100, 503100, 503101) or attempt == 3:
            raise WorkflowError(
                f"/make failed: HTTP={status}, code={code}, errors={sanitized_errors(body)}"
            )
        delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt - 1)
        time.sleep(min(delay, 30))
    raise WorkflowError(f"/make failed after bounded retries: {type(last_error).__name__}")


def poll_to_terminal(
    session: requests.Session,
    base_url: str,
    api_key: str,
    profile: dict[str, Any],
    conversation_id: str,
    interval: float,
) -> dict[str, Any]:
    last_snapshot: tuple[Any, Any, Any] | None = None
    while True:
        status, body, trace_id, _ = api_post(
            session,
            base_url,
            api_key,
            profile,
            "/poll",
            {"conversation_id": conversation_id},
        )
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        snapshot = (data.get("status"), data.get("current_node"), data.get("current_node_description"))
        if snapshot != last_snapshot:
            print(
                f"poll: request_id={trace_id}, HTTP={status}, code={body.get('code')}, "
                f"status={snapshot[0]}, node={snapshot[1]}, description={snapshot[2]}",
                flush=True,
            )
            last_snapshot = snapshot
        if snapshot[0] in TERMINAL_STATUSES:
            return data
        if status < 200 or status >= 300 or body.get("code") != 200:
            raise WorkflowError(f"/poll failed: HTTP={status}, code={body.get('code')}")
        time.sleep(interval)


def query_result_urls(
    session: requests.Session,
    base_url: str,
    api_key: str,
    profile: dict[str, Any],
    conversation_id: str,
    poll_data: dict[str, Any],
) -> dict[str, Any]:
    status, body, trace_id, _ = api_post(
        session,
        base_url,
        api_key,
        profile,
        "/queryResult",
        {"conversation_id": conversation_id},
    )
    data = require_success("/queryResult", status, body)
    final_result = data.get("final_video_result")
    if not isinstance(final_result, dict):
        final_result = {}
    video_url = data.get("video_url") or final_result.get("video_url") or poll_data.get("video_url")
    if not isinstance(video_url, str) or not video_url:
        raise WorkflowError("the completed task returned no video_url")
    poster_url = data.get("poster_url") or final_result.get("poster_url")
    if not isinstance(poster_url, str) or not poster_url:
        poster_url = None
    print(
        f"queryResult: request_id={trace_id}, HTTP={status}, code={body.get('code')}",
        flush=True,
    )
    return {
        "conversation_id": conversation_id,
        "status": "completed",
        "video_url": video_url,
        "poster_url": poster_url,
        "request_id": trace_id,
    }


def main() -> int:
    args = parse_args()
    profile = resolve_profile()
    base_url = profile["base_url"]
    if not 3 <= args.poll_interval <= 5:
        raise WorkflowError("--poll-interval must be between 3 and 5 seconds")
    paths = resolve_inputs(args.inputs)
    prepared = prepare_local_inputs(paths)
    if args.validate_only:
        counts = {kind: sum(item["asset_type"] == kind for item in prepared) for kind in ("image", "video")}
        print(
            f"validation: environment={profile['environment']}, images={counts['image']}, "
            f"videos={counts['video']}, API_requests=0",
            flush=True,
        )
        return 0

    if not args.intent:
        raise WorkflowError("--intent is required unless --validate-only is used")

    api_key = os.environ.get(profile["api_key_env"])
    if not api_key:
        raise WorkflowError(f"{profile['api_key_env']} is not configured")

    outer_request_id = args.outer_request_id or f"{profile['id_prefix']}-{uuid.uuid4().hex}"
    print(
        f"workflow: environment={profile['environment']}, outer_request_id={outer_request_id}",
        flush=True,
    )

    session = requests.Session()
    health_trace_id = new_request_id(profile, "health")
    health = session.get(
        f"{base_url}/api/rest/mva/health",
        headers={"X-Request-ID": health_trace_id},
        timeout=20,
    )
    print(f"health: request_id={health_trace_id}, HTTP={health.status_code}", flush=True)
    if health.status_code < 200 or health.status_code >= 300:
        raise WorkflowError(f"health check failed: HTTP={health.status_code}")

    assets = [
        upload_item(session, base_url, api_key, profile, item, index)
        for index, item in enumerate(prepared, start=1)
    ]
    make_data, make_trace_id = create_task(
        session,
        base_url,
        api_key,
        profile,
        {"user_intent": args.intent, "assets": assets, "outer_request_id": outer_request_id},
    )
    conversation_id = make_data["conversation_id"]
    print(f"task: conversation_id={conversation_id}", flush=True)
    if not args.wait:
        print(
            json.dumps(
                {
                    "conversation_id": conversation_id,
                    "status": make_data.get("status"),
                    "request_id": make_trace_id,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0

    poll_data = poll_to_terminal(
        session,
        base_url,
        api_key,
        profile,
        conversation_id,
        args.poll_interval,
    )
    if poll_data.get("status") != "completed":
        errors = poll_data.get("error_messages") if isinstance(poll_data.get("error_messages"), list) else []
        raise WorkflowError(f"task ended with status={poll_data.get('status')}, errors_count={len(errors)}")

    result = query_result_urls(
        session, base_url, api_key, profile, conversation_id, poll_data
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (WorkflowError, requests.RequestException, OSError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
