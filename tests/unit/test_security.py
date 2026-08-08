from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

PASSWORD = "secret-password-123"


# --- lozinke --------------------------------------------------------------


def test_hash_is_not_the_plaintext() -> None:
    hashed = hash_password(PASSWORD)

    assert hashed != PASSWORD
    assert PASSWORD not in hashed


def test_same_password_hashes_differently_each_time() -> None:
    """Argon2 koristi nasumicnu so -- dva heša iste lozinke se razlikuju."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_accepts_correct_password() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD))


def test_verify_rejects_wrong_password() -> None:
    assert not verify_password("pogresna", hash_password(PASSWORD))


# --- tokeni ---------------------------------------------------------------


def test_token_round_trip_preserves_payload() -> None:
    token = create_access_token({"sub": "42", "role": "ADMIN"})

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["role"] == "ADMIN"


def test_token_carries_expiry() -> None:
    payload = decode_access_token(create_access_token({"sub": "1"}))

    assert "exp" in payload


def test_expired_token_is_rejected() -> None:
    token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_another_key_is_rejected() -> None:
    forged = jwt.encode({"sub": "1"}, "tudji-kljuc-" + "x" * 32, algorithm=ALGORITHM)

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_tampered_payload_is_rejected() -> None:
    token = create_access_token({"sub": "1", "role": "USER"})
    header, payload, signature = token.split(".")
    forged_payload = jwt.utils.base64url_encode(b'{"sub":"1","role":"ADMIN"}').decode()

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(f"{header}.{forged_payload}.{signature}")


def test_none_algorithm_token_is_rejected() -> None:
    """Klasican napad: token bez potpisa sa `alg: none`."""
    unsigned = jwt.encode({"sub": "1"}, key="", algorithm="none")

    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_access_token(unsigned)


def test_secret_key_is_actually_used_for_signing() -> None:
    token = create_access_token({"sub": "1"})

    payload = jwt.decode(
        token, settings.secret_key.get_secret_value(), algorithms=[ALGORITHM]
    )

    assert payload["sub"] == "1"
