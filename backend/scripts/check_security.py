from backend.app.core.security import hash_password, verify_password


def main():
    password = "Example-only-password-123!"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != password
    print("PASS: Password is hashed")

    assert verify_password(password, first_hash)
    print("PASS: Correct password accepted")

    assert not verify_password("incorrect-password", first_hash)
    print("PASS: Wrong password rejected")

    assert first_hash != second_hash
    print("PASS: Unique salt produces different hashes")


if __name__ == "__main__":
    main()
