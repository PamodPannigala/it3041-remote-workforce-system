# IT3041 Remote Workforce System

A multi-agent remote workforce management web application.

---

## 1. Backend Setup & Instructions

### Environment Variables
Configure a `.env` file inside the `backend/` directory with the following variable names (never commit secret values):
- `MONGODB_HOST` — MongoDB cluster host URL
- `MONGODB_USERNAME` — Database user
- `MONGODB_PASSWORD` — Database password
- `MONGODB_DATABASE` — Database name
- `JWT_SECRET_KEY` — Cryptographic signing key for HS256 access tokens

To generate a secure 256-bit random key locally without exposing it:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Dependency Installation
Activate your Python virtual environment and install packages:

```powershell
# Production dependencies
pip install -r backend/requirements.txt

# Development & test dependencies
pip install -r backend/requirements-dev.txt
```

### Running the Backend Server
Start the FastAPI server on `http://127.0.0.1:8000`:

```powershell
uvicorn backend.app.main:app --reload
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### Running Backend Tests
```powershell
pytest backend/tests
```

Run baseline connectivity and security checks:
```powershell
python backend/scripts/check_security.py
python backend/scripts/check_db.py
```

---

## 2. Frontend Setup & Instructions

The frontend is built with React and Vite, using Vanilla CSS for a polished, responsive user experience.

### Dependency Installation
```powershell
cd frontend
npm install
```

### Running the Frontend Development Server
Start the Vite development server on `http://127.0.0.1:5173`:

```powershell
cd frontend
npm run dev
```

> **Note on API Proxy:** In development mode, Vite automatically proxies `/api/*` requests to the local backend at `http://127.0.0.1:8000/*`. This proxy configuration is for local development only.

### Running Frontend Tests & Production Build
```powershell
# Run Vitest test suite
cd frontend
npm test

# Build production bundle
npm run build
```

---

## 3. API Endpoints & Role Permission Matrix

| Endpoint | Method | Allowed Roles / Auth | Description |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | Public | Application liveness check |
| `/health/db` | `GET` | Public | MongoDB Atlas connectivity check |
| `/auth/register` | `POST` | Public | Create employee account (`extra="forbid"`, min 15-char password) |
| `/auth/login` | `POST` | Public | Authenticate user & issue 15-min JWT access token (`Cache-Control: no-store`) |
| `/auth/me` | `GET` | Authenticated (`employee`, `manager`, `admin`) | Retrieve current sanitized user profile |
| `/admin/access-check` | `GET` | `admin` | Administrative route guard verification |
| `/management/access-check` | `GET` | `manager`, `admin` | Management route guard verification |
| `/pulse-surveys/responses` | `POST` | `employee` | Submit weekly pulse survey response (server-derived user, team, week) |
| `/pulse-surveys/my-responses` | `GET` | `employee` | View authenticated employee's own pulse survey history |
| `/pulse-surveys/team-summary` | `GET` | `manager` | View privacy-thresholded team aggregate metrics (min 3 responses) |
| `/admin/pulse-surveys` | `GET` | `admin` | Audit pulse survey submission metadata (privacy-safe, read-only) |
| `/admin/pulse-surveys/summary` | `GET` | `admin` | Organization-wide per-team pulse summaries with privacy thresholding |

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

## 4. Current Architecture & Session Limitations

1. **In-Memory Session Storage:** JWT access tokens are stored strictly in-memory (React state) to prevent browser storage XSS exposure. Page reloads currently require signing in again.
2. **Token Lifetime & Refresh:** Access tokens expire in 15 minutes. Refresh tokens and server-side token revocation blocklists are not yet implemented.
3. **Dynamic Role Verification:** The backend resolves the token subject against the live database record on each request, ensuring role modifications or deactivations take effect immediately.
4. **Role Scope & Privacy Thresholding:** Weekly pulse surveys provide employee self-submission, manager team aggregates with a strict minimum response threshold of 3 for anonymity, and admin privacy-safe audit metadata. No individual well-being scores, mood/stress classifications, or diagnostic labels are computed or exposed.
5. **Specialist AI Agents:** The four specialist agents (*Productivity, Collaboration, Wellbeing, Task Assignment*) are designated for development on their respective feature branches; no synthetic results are simulated.
