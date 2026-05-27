# Microchore Backend

Django 5 + Django REST Framework API for **Microchore**, a viral-comment microtask platform: companies post target social-media posts, workers write authentic replies, reviewers approve or reject, and approved work earns payout.

## Stack

- Python 3.12, Django 5, Django REST Framework
- Simple JWT (access + refresh, refresh rotation, blacklist)
- SQLite for local dev (DATABASE_URL env switches to Postgres)
- Channels + Daphne (ASGI), Redis fallback to InMemory
- OAuth: Google sign-in, Twitter OAuth 2.0 PKCE, YouTube account linking

## Apps

| App | What lives there |
|---|---|
| `accounts` | Custom user, social accounts, holds, strikes, notifications, OAuth |
| `projects` | Project + Task models, company-side endpoints |
| `submissions` | Claim + Submission flow, reviewer hooks |
| `reviews` | Reviewer queue, tiers, decisions |
| `earnings` | Per-user payout summary |
| `verification` | Submission verification scaffolding |
| `ai_detection` | AI-text-detection service stub (env-driven) |
| `monitoring` | Operational metrics |
| `company_admin`, `workers` | Role-specific helpers |

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate       # macOS/Linux

pip install -r requirements.txt
copy .env.example .env            # then fill in SECRET_KEY etc.
python manage.py migrate
python manage.py seed_users       # seeds dev accounts (writer, reviewer, company, platform)
python manage.py runserver
```

API base: `http://127.0.0.1:8000/api/`.

## Tests

```bash
python manage.py test
```

10 tests cover the claim/submit/review path and reviewer-permission rules.

## Environment

See `.env.example`. Key variables:

- `SECRET_KEY`: required, must be at least 32 random chars in production
- `DEBUG`: `True` locally, `False` in production
- `ALLOWED_HOSTS`: comma-separated. For Cloudflare quick tunnel add `.trycloudflare.com`
- `CORS_ALLOWED_ORIGINS`: comma-separated list of frontend origins
- `FRONTEND_BASE_URL`: used for OAuth callbacks and email links
- `DATABASE_URL`: optional; if unset, SQLite at `db.sqlite3`
- `REDIS_URL`: optional; if unset, in-memory channels layer

## Expose to a deployed frontend (client demo)

For days-not-weeks demos, the project ships with `run-tunnel.bat`, which opens a Cloudflare quick tunnel pointing at port 8000. Run `python manage.py runserver` in one terminal and `run-tunnel.bat` in another. Copy the printed `*.trycloudflare.com` URL into the frontend's `VITE_API_URL` (e.g. Vercel env var) and into this backend's `CORS_ALLOWED_ORIGINS`. The URL rotates per restart.

Prereq: `winget install --id Cloudflare.cloudflared`.

For a stable URL, register a domain on Cloudflare and use `cloudflared tunnel create`.

## Companion repo

Frontend: [Microchore-Frontend](https://github.com/Hardik0110/Microchore-Frontend)

## Maintainer

Hardik Kubavat
