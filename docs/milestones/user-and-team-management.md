# Milestone: Controlled User and Team Management

## Overview & Architecture
This milestone introduces controlled user access and team management for the Remote Workforce System. It implements a secure CLI bootstrap command for the first administrator, comprehensive admin-only user and team management endpoints, strict database query scoping for managers and employees, and an extended React dashboard.

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 FastAPI Backend                        │
                  └────────────────────────────────────────────────────────┘
                                     │
      ┌──────────────────────────────┼──────────────────────────────┐
      │                              │                              │
┌─────▼───────────────┐   ┌──────────▼───────────────┐   ┌──────────▼───────────────┐
│ Admin API Endpoints │   │ Manager Scoped Endpoints │   │ Employee Team Summary    │
│  - /admin/users     │   │  - /teams/managed        │   │  - /teams/my-summary     │
│  - /admin/teams     │   │  - /teams/{id}/members   │   │                          │
│                     │   │    (scoped to managed)   │   │ (profile & summary only) │
│ (Last-admin &       │   │                          │   │ (cannot view other users)│
│  reassignment guard)│   │ (rejects other teams:403)│   │                          │
└─────────────────────┘   └──────────────────────────┘   └──────────────────────────┘
```

---

## 1. First-Admin CLI Bootstrap

To create the initial administrator without exposing passwords in arguments, logs, or command history:

### Exact Windows Command
```powershell
.\backend\.venv\Scripts\python backend\create_admin.py
```
*(Or if standard python is in PATH: `python backend\create_admin.py`)*

### Bootstrap Safeguards
- **Interactive Secure Prompting**: Uses Python's standard `getpass.getpass()` for password and confirmation entry. Passwords are never echoed or written to terminal buffers.
- **Strict Validation**: Reuses Pydantic email validation, normalization (lowercase and trimmed), and password length constraints (minimum 15 characters, maximum 128 characters).
- **Argon2 Hashing**: Uses the centralized `hash_password()` function to hash passwords with Argon2 before saving.
- **Admin Existence Guard**: Queries the `users` collection for any user with `role == "admin"`. If an admin account already exists, the script refuses execution with `PermissionError("Bootstrap refused: An administrator account already exists.")`.
- **Duplicate Account Protection**: Does not promote an existing employee or manager account; fails cleanly if an account with that email already exists.
- **No Automatic Cloud Execution**: The bootstrap script is designed to run locally on demand and is never executed automatically against live Atlas instances in test runs.

---

## 2. API Permission & Scoping Matrix

| Endpoint | Method | Allowed Roles | Description & Boundary Enforcement |
| :--- | :--- | :--- | :--- |
| `/auth/register` | POST | Anonymous | Self-registration. Creates `employee` account with `team_id: null`. |
| `/auth/login` | POST | Anonymous | Authenticates credentials and returns 15-minute HS256 JWT. |
| `/auth/me` | GET | All Authenticated | Resolves live user profile (`id`, `name`, `email`, `role`, `is_active`, `team_id`). |
| `/admin/users` | GET | `admin` | Paginated user list with safe fields (never exposes hashes). |
| `/admin/users/{id}/role` | PATCH | `admin` | Updates user role. Blocks self-demotion, last-admin demotion, and demoting actively assigned managers without reassigning their team. |
| `/admin/users/{id}/status` | PATCH | `admin` | Activates/deactivates user. Blocks self-deactivation, last-admin deactivation, and deactivating actively assigned managers. |
| `/admin/teams` | POST | `admin` | Creates a team with unique name and designated active manager. |
| `/admin/teams` | GET | `admin` | Lists all teams, assigned managers, and member rosters. |
| `/admin/teams/{id}/manager` | PATCH | `admin` | Reassigns team manager to another active user with role `manager`. |
| `/admin/teams/{id}/members` | POST | `admin` | Assigns/reassigns an employee to a team (single team constraint). |
| `/admin/teams/{id}/members/{uid}` | DELETE | `admin` | Unassigns employee from team (`team_id: null`). |
| `/teams/managed` | GET | `manager`, `admin` | Database query strictly filtered by `manager_id: current_user["_id"]`. Returns only teams managed by the caller. |
| `/teams/{id}/members` | GET | `admin`, or assigned `manager` | Returns member roster of the team. Returns HTTP 403 Forbidden if a manager attempts cross-team access. |
| `/teams/my-summary` | GET | All Authenticated | Returns team name and manager contact info for the caller's assigned team, or `has_team: false`. Cannot view other members. |

---

## 3. Data Models

### User Document (`users` collection)
```json
{
  "_id": "ObjectId(...)",
  "name": "Jane Doe",
  "email": "jane.doe@example.com",
  "password_hash": "$argon2id$v=19$...",
  "role": "employee",
  "is_active": true,
  "team_id": "ObjectId(...)",
  "created_at": "2026-09-20T06:00:00Z"
}
```

### Team Document (`teams` collection)
```json
{
  "_id": "ObjectId(...)",
  "name": "Frontend Engineering",
  "manager_id": "ObjectId(...)",
  "created_at": "2026-09-20T06:00:00Z"
}
```

- **Single Team Constraint**: An employee belongs to at most one team represented by `team_id` on the user record.
- **Manager Single-Assignment Rule**: A team references exactly one active manager (`manager_id`). If an admin attempts to demote or deactivate a manager who currently manages a team, the request is rejected until the team is reassigned.

---

## 4. Test Suites & Coverage Breakdown

### Isolated Backend Test Suite (Pytest)
All tests run with isolated in-memory fake database collections (`FakeAsyncDatabase` / `FakeAsyncCollection`), preventing pollution of live Atlas database instances.

1. `test_auth_register.py`: Tests email format, password complexity, duplicate email rejection, default employee role.
2. `test_auth_login_rbac.py`: Tests login, 15-minute JWT issuance, invalid credentials, dummy timing mitigation, expired tokens, tampered signatures, and RBAC access checks.
3. `test_create_admin_cli.py`: Tests bootstrap admin creation, rejection when admin exists, duplicate email rejection, and password policy validation.
4. `test_admin_user_management.py`: Tests admin pagination, safe response fields, role updates, status toggling, self-demotion protection, self-deactivation protection, last active admin protection, and active team manager reassignment protection.
5. `test_teams_and_ownership.py`: Tests team creation, manager role validation, member assignment/reassignment, manager scoped queries, rejection of cross-team access with manipulated IDs (HTTP 403), employee team summary, and restriction of member lists for employees.

### Frontend Test Suite (Vitest)
Unit and integration tests in `frontend/src/App.test.jsx` verify:
- Login and registration form validation and submission.
- Admin dashboard rendering with user directory, pagination, and team management controls.
- Manager dashboard rendering with managed team cards and member list.
- Employee dashboard rendering with assigned team summary and unassigned empty states.
- Clean presentation without test sandboxes or implementation-facing text.
- Footer rendering `IT3041 Remote Workforce System`.

### Manual Live Verification
The following end-to-end operational flow was verified against the live environment:
- **Initial Admin Bootstrap**: Successful bootstrap administrator creation via the local CLI tool.
- **Role Elevation**: Administrator successfully promoted a registered employee account (`Demo Employee Two`) to `manager`.
- **Team Creation & Manager Assignment**: Administrator created team `Team_Alpha` and designated `Demo Employee Two` as its active manager.
- **Member Assignment**: Administrator assigned employee `Pamod Sachintha` to `Team_Alpha`.
- **Scoped Employee Dashboard**: Authenticated employee dashboard loaded only `Team_Alpha` and its manager contact details, confirming horizontal isolation without access to other teams or user accounts.

---

## 5. Remaining Limitations

1. **Single Team Membership**: In this milestone, an employee belongs to at most one team. Cross-functional multiple-team assignments are not supported.
2. **Specialist AI Agents**: Productivity, Collaboration, Wellbeing, and Task Assignment agents are displayed as "Not implemented" pending their designated feature branches. No synthetic or simulated results are generated.
3. **No Task CRUD**: Task assignment and tracking models are deferred to subsequent feature milestones.

---

## 6. Five Viva Questions & Answers

1. **Q: Why does the system refuse the first-admin bootstrap script if an administrator account already exists?**  
   *A:* The bootstrap script is intended strictly for initial system initialization. Refusing execution if an admin already exists prevents unauthorized privilege escalation or accidental duplicate administrative account creation via the CLI.

2. **Q: How does the backend prevent an administrator from locking the system out of administrative access?**  
   *A:* The backend enforces two safeguards: (1) self-demotion/self-deactivation protection prevents the currently authenticated admin from demoting or deactivating their own account; (2) last active admin protection counts all active administrators in the database (`count_documents({"role": "admin", "is_active": True})`) and blocks any operation that would reduce the active admin count to zero.

3. **Q: Why is team scoping enforced at the database query level rather than just filtering records in the React frontend?**  
   *A:* Client-side filtering is insecure because an attacker can inspect network responses or craft direct API requests with modified team IDs. By scoping queries in the backend (e.g., `{"manager_id": current_user["_id"]}`), the server never transmits unauthorized data to the client, guaranteeing horizontal authorization boundaries.

4. **Q: What integrity constraint prevents orphaned teams when a manager's role is changed or their account is deactivated?**  
   *A:* The backend checks whether the user is referenced as `manager_id` in the `teams` collection before allowing a role change away from `manager` or deactivating the user. If an active team reference exists, the backend returns HTTP 400 Bad Request requiring the team to be reassigned first.

5. **Q: How does the team assignment enforce the single-team constraint for employees?**  
   *A:* The employee's `team_id` is stored directly on their user document. When an admin assigns an employee to a new team, a targeted `$set: {"team_id": new_team_id}` atomically overwrites any prior team assignment, ensuring each employee belongs to at most one team without race conditions or inconsistent join states.
