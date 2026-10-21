
from nudgeflow.security import hash_password, verify_password


def test_hash_password_does_not_return_plaintext():
    password = "Example-Password-123!"
    hashed_password = hash_password(password)

    assert hashed_password != password
    assert len(hashed_password) > 0


def test_verify_password_accepts_correct_password():
    password = "Example-Password-123!"
    hashed_password = hash_password(password)

    assert verify_password(password, hashed_password) is True


def test_verify_password_rejects_incorrect_password():
    hashed_password = hash_password("Example-Password-123!")

    assert verify_password("Wrong-Password-123!", hashed_password) is False
