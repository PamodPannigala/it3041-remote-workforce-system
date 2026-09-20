# IT3041 Remote Workforce System

A multi-agent remote workforce management web application.

---

## Backend Setup & Instructions

### 1. Environment Variables
Configure a `.env` file inside the `backend/` directory with the following variable names (never commit secret values):
- `MONGODB_HOST` — MongoDB cluster host URL
- `MONGODB_USERNAME` — Database user
- `MONGODB_PASSWORD` — Database password
- `MONGODB_DATABASE` — Database name
- `JWT_SECRET_KEY` — Cryptographic signing key for HS256 access tokens

To generate a secure 256-bit random key locally without exposing it:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Dependency Installation
Activate your Python virtual environment and install packages:

```bash
# Production dependencies
pip install -r backend/requirements.txt

# Development & test dependencies
pip install -r backend/requirements-dev.txt
```

### 3. Running the Server
Start the FastAPI server with auto-reload:

```bash
python -m uvicorn main:app --app-dir backend --reload
```

Interactive API documentation will be available at `http://127.0.0.1:8000/docs`.

### 4. Running Automated Tests & Checks
Run the isolated automated test suite:

```bash
pytest backend/tests
```

Run baseline connectivity and security checks:

```bash
python backend/check_security.py
python backend/check_db.py
```

---

## API Endpoints & Role Permission Matrix

| Endpoint | Method | Allowed Roles / Auth | Description |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | Public | Application liveness check |
| `/health/db` | `GET` | Public | MongoDB Atlas connectivity check |
| `/auth/register` | `POST` | Public | Create employee account (`extra="forbid"`, min 15-char password) |
| `/auth/login` | `POST` | Public | Authenticate user & issue 15-min JWT access token (`Cache-Control: no-store`) |
| `/auth/me` | `GET` | Authenticated (`employee`, `manager`, `admin`) | Retrieve current sanitized user profile |
| `/admin/access-check` | `GET` | `admin` | Administrative route guard verification |
| `/management/access-check` | `GET` | `manager`, `admin` | Management route guard verification |

### JSON Login Request Example
```json
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "YourSecurePassword123!"
}
```

**Successful Response (HTTP 200):**
```json
{
  "access_token": "<jwt-token-string>",
  "token_type": "bearer",
  "expires_in": 900
}
```

---

## Current Architecture & Limitations

1. **Access Tokens & Expiration:** JWT access tokens are signed using `HS256` with strict claim verification (`sub`, `iat`, `exp`, `iss`, `aud`) and an expiration window of 15 minutes.
2. **Dynamic Role Verification:** Token subject (`sub`) is resolved against the live database record on each request, ensuring role changes or account deactivations take effect immediately.
3. **No Refresh Tokens / Revocation List:** Refresh tokens and immediate revocation token blocklists are not yet implemented.
4. **Role Scope:** Current role checks verify global role levels (`employee`, `manager`, `admin`). Team-level or resource-level ownership constraints are not yet implemented.
5. **Rate Limiting:** Rate limiting for login and registration attempts is not yet active.
