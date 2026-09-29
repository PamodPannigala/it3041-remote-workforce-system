from backend.app.core.rate_limiting import limiter
from backend.tests.auth.test_auth_login_rbac import create_test_user


def _login(client, email, password):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )


def test_cors_allows_local_frontend_and_rejects_unknown_origin(test_setup):
    client, _ = test_setup

    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    rejected = client.get("/health", headers={"Origin": "https://attacker.example"})

    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert rejected.headers.get("Access-Control-Allow-Origin") is None


def test_auth_rate_limit_rejects_sixth_login_and_allows_first_five(test_setup):
    client, _ = test_setup
    responses = [
        _login(client, "unknown@example.com", "WrongPassword123!")
        for _ in range(6)
    ]

    assert [response.status_code for response in responses[:5]] == [401] * 5
    assert responses[5].status_code == 429
    assert responses[5].json() == {
        "detail": "Too many requests. Please try again later."
    }


def test_auth_rate_limit_rejects_sixth_registration(test_setup):
    client, _ = test_setup
    responses = [
        client.post(
            "/auth/register",
            json={
                "name": f"New User {index}",
                "email": f"new-user-{index}@example.com",
                "password": "SecurePassword123!#$",
            },
        )
        for index in range(6)
    ]

    assert [response.status_code for response in responses[:5]] == [201] * 5
    assert responses[5].status_code == 429
    assert responses[5].json() == {
        "detail": "Too many requests. Please try again later."
    }


def test_cors_preflight_allows_frontend_headers_and_methods(test_setup):
    client, _ = test_setup

    response = client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert "POST" in response.headers.get("Access-Control-Allow-Methods", "")
    assert "authorization" in response.headers.get("Access-Control-Allow-Headers", "").lower()
    assert "content-type" in response.headers.get("Access-Control-Allow-Headers", "").lower()


def test_successful_login_within_auth_limit_is_unaffected(test_setup):
    client, _ = test_setup
    password = "CorrectSecretPassword123!"
    create_test_user(client.app.state.database, "within-limit@example.com", password)

    response = _login(client, "within-limit@example.com", password)

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_general_rate_limit_applies_to_other_routes(test_setup):
    client, _ = test_setup

    responses = [client.get("/health") for _ in range(101)]

    assert all(response.status_code == 200 for response in responses[:100])
    assert responses[100].status_code == 429
    assert responses[100].json() == {
        "detail": "Too many requests. Please try again later."
    }


def test_account_lockout_and_other_account_independence(test_setup):
    client, fake_db = test_setup
    locked_password = "CorrectSecretPassword123!"
    other_password = "OtherCorrectPassword123!"
    locked_user = create_test_user(fake_db, "locked@example.com", locked_password)
    create_test_user(fake_db, "unrelated@example.com", other_password)

    failed = [
        _login(client, "locked@example.com", "WrongPassword123!")
        for _ in range(5)
    ]
    assert all(response.status_code == 401 for response in failed)
    assert locked_user["failed_login_attempts"] == 5
    assert locked_user["locked_until"] is not None

    limiter.reset()
    locked_response = _login(client, "locked@example.com", locked_password)
    wrong_password_response = _login(
        client, "unrelated@example.com", "WrongPassword123!"
    )
    unrelated_success = _login(client, "unrelated@example.com", other_password)

    assert locked_response.status_code == wrong_password_response.status_code == 401
    assert locked_response.json() == wrong_password_response.json()
    assert locked_response.headers.get("WWW-Authenticate") == wrong_password_response.headers.get("WWW-Authenticate") == "Bearer"
    assert unrelated_success.status_code == 200


def test_successful_login_resets_failed_attempts(test_setup):
    client, fake_db = test_setup
    password = "CorrectSecretPassword123!"
    user = create_test_user(fake_db, "reset-counter@example.com", password)

    for _ in range(4):
        assert _login(client, "reset-counter@example.com", "WrongPassword123!").status_code == 401
    assert user["failed_login_attempts"] == 4

    limiter.reset()
    assert _login(client, "reset-counter@example.com", password).status_code == 200
    assert user["failed_login_attempts"] == 0
    assert user["locked_until"] is None

    limiter.reset()
    for _ in range(4):
        assert _login(client, "reset-counter@example.com", "WrongPassword123!").status_code == 401
    still_unlocked = _login(client, "reset-counter@example.com", password)
    assert still_unlocked.status_code == 200


def test_standard_security_headers_are_present(test_setup):
    client, _ = test_setup

    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "Strict-Transport-Security" not in response.headers