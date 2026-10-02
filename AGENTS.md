# Instructions for Codex

You are one of two coding agents on TalkBack. The other is Claude Code. Read [docs/plan.md](docs/plan.md) first: it says who owns which files.

## Your area

- You own `backend/` and `eval/`. Your work packages are X1–X9 in docs/plan.md section 5.
- Do not edit `frontend/`. It belongs to Claude Code.
- `backend/app/protocol.py` and `docs/architecture.md` section 3 are the shared contract. Change them only in a separate "contract" pull request (docs/plan.md section 4).

## Before you code

Read `docs/prd.md`, `docs/architecture.md`, `SECURITY.md` and `docs/plan.md`. Architecture and SECURITY.md are the source of truth.

## Workflow

- Branch: `codex/<task>`. Never commit to `main` directly.
- Before a pull request: `git fetch origin && git rebase origin/main`, then run the tests.
- Setup and tests:
  ```bash
  cd backend
  python -m venv .venv
  .venv/bin/python -m pip install -r requirements-dev.txt   # Windows: .venv\Scripts\python
  .venv/bin/python -m pytest
  ```
- Run the server: `.venv/bin/python -m uvicorn app.main:app --port 8000 --ws-max-size 65536`

## Rules

- Follow SECURITY.md section 5. API keys only in `backend/.env`, never in code, logs or commits.
- Pin exact versions in `requirements.txt`. Keep dependencies minimal.
- Every package needs tests, including the SECURITY.md section 6 tests that apply.
- Logs are JSON with `session_id` and `turn_id`; no audio, no keys, no transcript text.
- Match the existing code style in `backend/app/`.
