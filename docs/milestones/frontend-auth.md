# Milestone: React Frontend Authentication & Authenticated Dashboard

## Overview & Request Flow
This milestone implements a React (Vite) single-page frontend connecting to the existing FastAPI backend. The frontend manages user registration, JWT authentication, in-memory session state, and role-based dashboard views.

```
Client Browser (React SPA)
   │
   ├─► POST /api/auth/register ──► [Vite Dev Proxy: /api -> :8000] ──► FastAPI backend
   │                                                                       │ (Enforces role="employee",
   │                                                                       │  hashes password via Argon2,
   │                                                                       │  creates unique index in Mongo)
   │
   ├─► POST /api/auth/login ─────► [Vite Dev Proxy: /api -> :8000] ──► FastAPI backend
   │                                                                       │ (Validates credentials,
   │                                                                       │  issues 15-min HS256 JWT)
   │
   ├─► GET /api/auth/me ─────────► [Vite Dev Proxy: /api -> :8000] ──► FastAPI backend
   │     (Bearer <token>)                                                  │ (Resolves live user profile
   │                                                                       │  and DB role verification)
   │
   └─► Render Dashboard:
         - Verified user name, email, and role badge
         - Live RBAC Guard check buttons (/management/access-check, /admin/access-check)
         - 4 Specialist Agent Cards marked "Not implemented" (Pending feature branches)
```

## Security & Session Architecture
1. **In-Memory JWT Storage:** Access tokens are held exclusively in React state (`AuthContext`), protecting against XSS-based local storage scraping.
2. **Page Reload Policy:** In-memory session means page refresh requires re-authentication.
3. **Session Expiration:** Received HTTP 401 on authenticated requests immediately resets user session state and redirects to login.
4. **Role Enforcement:** HTTP 403 Forbidden responses display an access denied alert without terminating the authenticated session.
5. **No Synthetic Metric Simulation:** The dashboard displays real verified user identity and transparently flags future specialist modules as "Not implemented".

## Changed & Created Files
- `frontend/package.json`: Node dependencies (React 18, Vite 5, Vitest, Testing Library).
- `frontend/package-lock.json`: Committed dependency lockfile.
- `frontend/vite.config.js`: Vite server configuration with development proxy (`/api` -> `http://127.0.0.1:8000`) and Vitest configuration.
- `frontend/index.html`: Web page entry point with responsive viewport and Google Fonts (Inter).
- `frontend/src/index.css`: Comprehensive design system with CSS custom properties, responsive layout, card containers, alerts, and micro-animations.
- `frontend/src/api/auth.js`: Modular API client handling register, login, profile fetch, and RBAC endpoint calls.
- `frontend/src/context/AuthContext.jsx`: Context provider managing in-memory session token, user data, login/logout transitions, and 401 handling.
- `frontend/src/components/Navbar.jsx`: Header with brand title, version tag, active user badge, and sign-out button.
- `frontend/src/components/LoginForm.jsx`: Login card with email/password validation, error banners, and loading spinner.
- `frontend/src/components/RegisterForm.jsx`: Registration card with field validations (min 15-char password, password confirmation match).
- `frontend/src/components/Dashboard.jsx`: Verified user profile card, RBAC sandbox check buttons, and specialist agent module cards.
- `frontend/src/App.jsx`: Root application coordinator.
- `frontend/src/test/setup.js`: Vitest test setup file.
- `frontend/src/App.test.jsx`: Unit test suite for frontend auth, validations, dashboard rendering, and RBAC checks.
- `docs/milestones/frontend-auth.md`: Milestone architecture and viva preparation document.

## Testing & Verification Summary
- **Frontend Unit Tests (Vitest):** `6/6 passed` (testing login, registration, validation, identity loading, 403 handling, and logout).
- **Frontend Production Build:** `npm run build` succeeded (`dist/` generated cleanly).
- **Backend Test Suite (Pytest):** `17/17 passed` (all registration, JWT, and RBAC tests isolated from live Atlas database).
- **Browser End-to-End Smoke Test:** Executed against live local FastAPI backend and Vite frontend dev server. Completed all 11 steps including synthetic user registration, login, authenticated dashboard loading, 403 RBAC verification, and logout.

## Five Viva Questions & Answers

1. **Q: Why are JWT access tokens kept in memory instead of `localStorage` or `sessionStorage`?**  
   *A:* Storing tokens in `localStorage` exposes them to Cross-Site Scripting (XSS) attacks because any JavaScript running in the browser can read `localStorage`. Keeping the token in React state/memory ensures it cannot be accessed directly by unauthorized client scripts.

2. **Q: How does the Vite development proxy work and why is it used?**  
   *A:* The Vite development proxy forwards browser requests made to `/api/*` directly to `http://127.0.0.1:8000/*`. This avoids browser Cross-Origin Resource Sharing (CORS) preflight issues during local development without needing overly permissive wildcard CORS headers on the backend.

3. **Q: What is the sequence of events after a user enters credentials on the login form?**  
   *A:* First, `loginUser` sends `POST /api/auth/login`. Upon receiving a 200 OK with `access_token`, the application calls `getMe(accessToken)` (`GET /api/auth/me`) with `Authorization: Bearer <token>` to verify identity and fetch the latest database-backed role before rendering the dashboard.

4. **Q: How does the frontend handle HTTP 401 vs HTTP 403 responses differently?**  
   *A:* An HTTP 401 Unauthorized indicates that the token is invalid, tampered, or expired; the frontend immediately clears the session and returns to the login screen. An HTTP 403 Forbidden indicates the user is authenticated but lacks required role permissions for that resource; the frontend displays an "Access Denied" notice while preserving the user's active session.

5. **Q: Why are specialist AI agents displayed as "Not implemented" rather than generating simulated output?**  
   *A:* Per responsible AI engineering and academic integrity principles, incomplete modules should never display fabricated or mock metric calculations. Flagging them transparently as "Not implemented" indicates that their implementation belongs to future feature branches.
