import pytest
from fastapi import HTTPException

from app.api.public.deps import (
    get_enabled_credential,
    parse_api_credentials,
    sign_payload,
    signature_payload,
    validate_timestamp,
    verify_signature,
)


def test_parse_api_credentials_from_json_object() -> None:
    credentials = parse_api_credentials(
        '{"partner":{"secret":"secret-value","enabled":true}}'
    )

    assert credentials["partner"].secret == "secret-value"
    assert credentials["partner"].enabled is True


def test_disabled_api_credential_is_rejected() -> None:
    credentials = parse_api_credentials(
        '{"partner":{"secret":"secret-value","enabled":false}}'
    )

    with pytest.raises(HTTPException) as exc_info:
        get_enabled_credential("partner", credentials)

    assert exc_info.value.status_code == 401


def test_signature_verification_uses_canonical_payload() -> None:
    payload = signature_payload(
        method="GET",
        path="/api/v1/notices",
        canonical_query="country=DEU&page=1&per_page=20",
        timestamp="1800000000",
        nonce="nonce-1",
        body_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    signature = sign_payload("secret-value", payload)

    assert verify_signature(
        secret="secret-value",
        expected_signature=signature,
        method="GET",
        path="/api/v1/notices",
        canonical_query="country=DEU&page=1&per_page=20",
        timestamp="1800000000",
        nonce="nonce-1",
        body=b"",
    )


def test_timestamp_outside_ttl_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_timestamp("100", ttl_seconds=300, now=1000)

    assert exc_info.value.status_code == 401
