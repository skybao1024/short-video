import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlencode

from fastapi import Header, HTTPException, Request, status
from redis.exceptions import RedisError

from app.core.config import settings
from app.services.common.redis import redis_client


@dataclass(frozen=True)
class ApiCredential:
    api_key: str
    secret: str
    enabled: bool = True


def parse_api_credentials(raw_json: str) -> dict[str, ApiCredential]:
    if not raw_json:
        return {}
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError("API_KEYS_JSON must be valid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("API_KEYS_JSON must be a JSON object")

    credentials: dict[str, ApiCredential] = {}
    for api_key, value in raw.items():
        if isinstance(value, str):
            credentials[api_key] = ApiCredential(api_key=api_key, secret=value)
            continue
        if not isinstance(value, dict) or not value.get("secret"):
            raise ValueError(f"API key {api_key} must define a secret")
        credentials[api_key] = ApiCredential(
            api_key=api_key,
            secret=str(value["secret"]),
            enabled=bool(value.get("enabled", True)),
        )
    return credentials


def canonical_query_string(query_params) -> str:
    pairs = sorted((key, value) for key, value in query_params.multi_items())
    return urlencode(pairs)


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def signature_payload(
    *,
    method: str,
    path: str,
    canonical_query: str,
    timestamp: str,
    nonce: str,
    body_hash: str,
) -> str:
    return "\n".join(
        [method.upper(), path, canonical_query, timestamp, nonce, body_hash]
    )


def sign_payload(secret: str, payload: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_signature(
    *,
    secret: str,
    expected_signature: str,
    method: str,
    path: str,
    canonical_query: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> bool:
    payload = signature_payload(
        method=method,
        path=path,
        canonical_query=canonical_query,
        timestamp=timestamp,
        nonce=nonce,
        body_hash=sha256_hex(body),
    )
    actual_signature = sign_payload(secret, payload)
    return hmac.compare_digest(actual_signature, expected_signature)


def validate_timestamp(
    timestamp: str, ttl_seconds: int, now: int | None = None
) -> None:
    try:
        request_time = int(timestamp)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Timestamp",
        ) from exc

    current_time = int(time.time()) if now is None else now
    if abs(current_time - request_time) > ttl_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expired X-Timestamp",
        )


def get_enabled_credential(
    api_key: str, credentials: Mapping[str, ApiCredential]
) -> ApiCredential:
    credential = credentials.get(api_key)
    if credential is None or not credential.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return credential


async def ensure_nonce_not_replayed(api_key: str, nonce: str, ttl_seconds: int) -> None:
    key = f"api_nonce:{api_key}:{nonce}"
    try:
        inserted = await redis_client.redis.set(key, "1", ex=ttl_seconds, nx=True)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nonce verification unavailable",
        ) from exc
    if not inserted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Replayed X-Nonce",
        )


async def require_aksk(
    request: Request,
    x_api_key: str = Header(..., alias="X-Api-Key"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
) -> ApiCredential:
    credentials = parse_api_credentials(settings.API_KEYS_JSON)
    credential = get_enabled_credential(x_api_key, credentials)
    validate_timestamp(x_timestamp, settings.API_SIGNATURE_TTL_SECONDS)

    body = await request.body()
    is_valid = verify_signature(
        secret=credential.secret,
        expected_signature=x_signature,
        method=request.method,
        path=request.url.path,
        canonical_query=canonical_query_string(request.query_params),
        timestamp=x_timestamp,
        nonce=x_nonce,
        body=body,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    await ensure_nonce_not_replayed(
        api_key=credential.api_key,
        nonce=x_nonce,
        ttl_seconds=settings.API_SIGNATURE_TTL_SECONDS,
    )
    return credential
