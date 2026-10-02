# Instructions for Claude Code

You are one of two coding agents on TalkBack. The other is Codex. Read [docs/plan.md](docs/plan.md) first: it says who owns which files.

## Your area

- You own `frontend/`. Your work packages are Phase 0 and F1–F8 in docs/plan.md.
- Do not edit `backend/` or `eval/`. They belong to Codex. Phase 0 (the contract) is the only exception.
- `backend/app/protocol.py` and `docs/architecture.md` section 3 are the shared contract. Change them only in a separate "contract" pull request.

## Before you code

Read `docs/design.md` and `frontend/src/styles/tokens.css` before any UI work, plus `docs/architecture.md` and `SECURITY.md`. Follow design.md section 10 (build order, design skills, all states, final checks).

## Workflow

- Branch: `claude/<task>`. Never commit to `main` directly.
- Before a pull request: `git fetch origin && git rebase origin/main`, then `cd frontend && npm run build && npm run lint`.
- Use only design tokens; Tailwind's default palette and spacing are disabled on purpose.
- Pin exact versions (`frontend/.npmrc` has `save-exact=true`).
