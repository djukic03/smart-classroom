from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)

PASSWORD = "secret-password-123"


def test_hash_is_not_the_plaintext() -> None:
    hashed = hash_password(PASSWORD)

    assert hashed != PASSWORD
    assert PASSWORD not in hashed


def test_same_password_hashes_differently_each_time() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_accepts_correct_password() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD))


def test_verify_rejects_wrong_password() -> None:
    assert not verify_password("pogresna", hash_password(PASSWORD))


def test_generated_tokens_are_unique() -> None:
    tokens = {generate_token() for _ in range(100)}

    assert len(tokens) == 100


def test_generated_token_is_long_enough() -> None:
    assert len(generate_token()) >= 40


def test_token_hash_is_not_the_token() -> None:
    token = generate_token()

    assert hash_token(token) != token


def test_token_hash_is_stable() -> None:
    token = generate_token()

    assert hash_token(token) == hash_token(token)


def test_different_tokens_hash_differently() -> None:
    assert hash_token(generate_token()) != hash_token(generate_token())


def test_token_hash_fits_the_column() -> None:
    assert len(hash_token(generate_token())) == 64
