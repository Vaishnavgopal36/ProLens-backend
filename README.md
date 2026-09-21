# ProLens Backend

Multi-tenant project management API built with FastAPI, SQLAlchemy 2 and PostgreSQL.
Tenant isolation is enforced twice: by the service layer and by Postgres row level
security (RLS) driven by per-request `SET LOCAL app.*` settings.

## Setup

Requirements: Python 3.10+, PostgreSQL, an S3-compatible bucket (Supabase Storage).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # or create .env by hand, see "Environment variables"
alembic upgrade head        # uses MIGRATION_DATABASE_URL
uvicorn app.main:app --reload
```

The API listens on http://localhost:8000 (interactive docs at `/docs`, liveness at `/health`).

### Docker

```bash
docker compose up --build
```

`docker-compose.yml` starts the `api` service (uvicorn with reload) and the `worker`
service (outbox worker, see below). The image runs as a non-root user and has a
`HEALTHCHECK` on `/health`. `.env` is not baked into the image; it is injected by compose.

## Environment variables

All settings are defined in `app/core/config.py` and read from the environment or `.env`.

| Variable | Default | Description |
| --- | --- | --- |
| `MIGRATION_DATABASE_URL` | required | DB URL for Alembic (owner role, bypasses RLS). |
| `APP_DATABASE_URL` | required | DB URL for the API (non-owner role so RLS applies). |
| `JWT_SECRET_KEY` | required | Secret used to sign access tokens. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token and access cookie lifetime. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token, session and refresh cookie lifetime. |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Public URL of this API (SSO redirect URIs). |
| `SUPABASE_S3_ENDPOINT` | required | S3-compatible endpoint of Supabase Storage. |
| `SUPABASE_S3_REGION` | `us-east-1` | Storage region. |
| `SUPABASE_S3_ACCESS_KEY_ID` | required | Storage access key id. |
| `SUPABASE_S3_SECRET_ACCESS_KEY` | required | Storage secret key. |
| `SUPABASE_S3_BUCKET` | `attachments` | Bucket for attachments. |
| `ATTACHMENT_URL_EXPIRE_SECONDS` | `300` | Lifetime of signed attachment URLs. |
| `ATTACHMENT_MAX_SIZE_BYTES` | `26214400` | Maximum attachment size (25 MiB). |
| `CORS_ALLOWED_ORIGINS` | `["http://localhost:5173"]` | JSON list of browser origins allowed to call the API with cookies. |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | Frontend URL used in links (emails, redirects). |
| `PASSWORD_MIN_LENGTH` | `8` | Minimum password length (max is 72 bytes, a bcrypt limit). |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `5` | Failed logins allowed per client IP + email per window. |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `300` | Sliding window for the login limiter. |
| `BREVO_API_KEY` | unset | Brevo API key (v3, `xkeysib-…`). When set, emails go through Brevo's HTTPS API and the SMTP settings are ignored. |
| `SMTP_HOST` | unset | SMTP server. Used when `BREVO_API_KEY` is unset. When both are unset, emails are logged instead of sent. |
| `SMTP_PORT` | `587` | SMTP port. |
| `SMTP_USERNAME` | unset | SMTP user. |
| `SMTP_PASSWORD` | unset | SMTP password. |
| `SMTP_USE_TLS` | `true` | Use STARTTLS. |
| `EMAIL_FROM` | `ProLens <no-reply@prolens.local>` | Sender address. With Brevo it must be a sender verified in Brevo. |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `2.0` | Worker poll interval. |
| `OUTBOX_BATCH_SIZE` | `10` | Outbox rows processed per poll. |
| `OUTBOX_MAX_ATTEMPTS` | `5` | Delivery attempts before a row is marked failed. |
| `OUTBOX_RETRY_BASE_SECONDS` | `30` | Base delay for retry backoff. |

## Architecture

```
app/
  main.py            app factory: routers, CORS, exception handlers
  api/               deps (auth, RBAC), pagination, routes (thin HTTP layer)
  services/          business rules; raise AppException subclasses
  repositories/      SQLAlchemy queries; soft-delete aware
  schemas/           Pydantic request/response models mirroring DB constraints
  models/            SQLAlchemy models
  core/              config, security, cookies, rate limiting, errors, storage
alembic/             migrations (including RLS policies)
```

Layering: route -> service(db) -> repository(db). Routes own the transaction and call
`db.commit()`; services and repositories only `flush()` (a commit would drop the
`SET LOCAL` RLS context). Services raise `AppException` subclasses, which the app turns
into the common envelope `{status_code, status_message, error_message, response_data}`.

Authentication: JWT access token and opaque refresh token in httpOnly cookies
(`access_token` on `/`, `refresh_token` on `/auth`). Refresh sessions are stored hashed
and revoked on refresh, logout, user deletion and suspension. Deleted or suspended users
and organizations are rejected on every request by `get_current_user`.
Roles: `super_admin` > `admin` > `manager` > `employee`.

The login rate limiter is in memory and therefore per process.

### Outbox worker

Asynchronous work (emails, reports) goes through a Postgres-backed outbox processed by a
separate process:

```bash
python -m app.worker
```

In Docker it runs as the compose service `worker`.

## Real-time discussion (WebSocket)

Endpoint: `WS /ws/projects/{project_id}/discussion`.

- **Auth:** same HttpOnly `access_token` cookie and validation as REST
  (`authenticate_access_token` in `app/api/deps.py`). Access rule is the same as the
  REST discussion (active project in the caller's org, member or admin/super_admin).
  Rejections happen before the socket is accepted (close 4401 unauthenticated,
  4404 no access, 4403 bad origin; browsers see a failed handshake, HTTP 403).
- **Origin:** if an `Origin` header is sent it must be in `CORS_ALLOWED_ORIGINS`.
  A missing `Origin` (non-browser client) is allowed.
- **Limits:** max 5 sockets per user and project (the oldest is closed with 4409);
  text frames over 1 KiB close with 1009; the server closes with 4401 when the access
  token expires so the client reconnects with fresh cookies.
- **Server frames:** `{"type":"ready"}`, `{"type":"message.created"|"message.updated","data":<DiscussionMessage>}`,
  `{"type":"message.deleted","data":{"id","project_id"}}`, `{"type":"pong"}`.
  **Client frames:** only `{"type":"ping"}`; anything else is ignored.
- Events are published after the DB commit (discussion POST, and comment PATCH/DELETE
  for project comments only).
- **Limitation:** fan-out is in-process, so it only works with a single backend
  process. See `TECH_DEBT.md` (item 2) for the multi-process plan.

## Testing

```bash
PYTHONPATH=. python -m pytest -q
```

Tests use a stubbed database session and dependency overrides (`tests/conftest.py`), so
no database or storage is needed.

Lint and format: `ruff format <files> && ruff check <files>`.
