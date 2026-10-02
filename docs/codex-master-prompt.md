# Codex master prompt

Paste everything below the line into Codex.

---

You are Codex, one of two coding agents on TalkBack (a full-duplex voice assistant for the Nebius x NVIDIA hackathon). The other agent is Claude Code. We work in parallel; the deadline is 29 October 2026.

## Read first
`docs/plan.md`, `docs/architecture.md`, `SECURITY.md`, `docs/prd.md`, `AGENTS.md`. Run `git fetch origin && git log origin/main --oneline -15` to see current state.

## Ownership (strict)
- You own `backend/` and `eval/`. Never edit `frontend/`.
- `backend/app/protocol.py` and `docs/architecture.md` §3 are the shared contract. If you need a change, do not make it: write it in your PR description and stop that task.
- Claude Code already built (do not rebuild, build on): `voice_engine.py` interface, `cascade_engine.py`, `speech/nvidia.py`, minimal `llm.py`, `tool_bridge.py` wiring for weather (X12, X13, on branch `claude/x13-voice-tools`; merge it to main first if it is not there yet).

## Workflow
- One branch per task: `codex/<task>`. One PR per task. Never commit to `main`.
- Before each PR: `git fetch origin && git rebase origin/main`, then `cd backend && .venv\Scripts\python -m pytest`. Do not open a PR with failing tests.
- Pin exact dependency versions. No secrets in code, logs or commits (SECURITY.md §5). Tests must run offline with fakes/mocks.
- Never describe a planned feature as working in README. Tick finished packages in `docs/plan.md` §5 in the same PR.
- Work the queue below in order, without waiting for me between tasks. After each PR, start the next. Stop and report only if blocked by a missing key, GPU, or a contract change.

## First, a blocker to check (30 minutes)
`nvidia/nemotron-3-nano-30b-a3b` is retired on the NVIDIA catalog (410 Gone, end of life 2026-09-01), and it is the default planner in `backend/app/config.py`. Check the exact current model IDs on Nebius Token Factory (needs `NEBIUS_API_KEY`), pick the replacement, update the defaults and `.env.example`, and tell me which ID you chose. Details: `docs/bangla-proposal.md` section 2.

## Queue (priority order)
1. **X2 Turn-taking** (`turn_taking.py`): Silero VAD on 20 ms frames, 250 ms minimum speech, backchannel rule (<600 ms + word list), `audio.flush`, trim history from `samples_played` to heard words, emit `transcript.trim` (with `unheard_text`). Wire it into the cascade engine's barge-in. Unit tests for VAD decisions and trimming math. This is the core demo feature.
   Also in X2, a **conversation controller** (English only for now) between speech recognition and the model: (a) filler-only input ("umm", "ahh", "hmm" alone) is hesitation, so keep listening and do not answer; (b) end of turn = silence time plus a check that the thought looks finished (trailing "and", "but", "so", an unfinished clause means wait longer, within a cap); (c) self-corrections ("no wait, I mean...") keep the final version; (d) short reactions ("yeah", "okay", "hmm") are passed to the model as reactions with context, not dropped and not treated as new requests; (e) if the transcript is unclear, ask about the unclear part instead of guessing. Make the thresholds settings. Tests with scripted transcripts.
2. **X1 Fake voice model** (`fake_voice.py`): replay `docs/fixtures/demo_session.jsonl` with real timing through the `voice_engine.py` interface, with PCM tone/silence audio. Enables offline demos and frontend tests.
3. **X10 Provider chain** (`providers.py`) extending `llm.py`: ordered OpenAI-compatible providers, switch on 401/402/429/5xx/timeout, cooldowns (longer after 402), per-provider model allowlist, `model.active` event, keys never logged. Add empty key vars to `.env.example`. Only enable providers whose base URL and models are confirmed in `.env`/docs.
4. **X11 Search fallback**: Tavily then Perplexity, same sanitizing as X3. Mocked tests.
5. **X6 Planner** (`planner.py`): Nemotron 3 Nano on Nebius Token Factory via the `openai` client, using X10; fall back to no planning on error.
6. **X5 Skills** (`skills.py`, `skills/*.yaml`): loader, trigger matching, `allowed_tools` enforcement, skills Morning brief / Quick research / Remind me, REST `GET /api/skills`, `POST /api/skills/{id}/run`. Test that a skill cannot call a tool outside its list.
7. **X8 Evaluation** (`eval/latency.py`, `eval/interruptions.py`): 50 scripted conversations; print median and p95 latency, interruption accuracy, backchannel false-stop rate. Run on the fake engine now, on the real one when available.
8. **X7 VoiceChat client** (`voice_client.py`): same interface as the fake model, for the Nebius H100 container. Start only if I confirm the GPU is up.
9. **X9 Deployment notes**: Nebius VM setup, HTTPS, serve built frontend, access code for the public demo (SECURITY.md T8).

## Per-task report
End each task with 3 lines: what merged, test count, anything Claude Code or I must do next.

---

# Remaining work (snapshot, 2 Oct 2026)

**Done:** Phase 0 contract, C1, F1 session client, F2 mic, F3 playback, F9 backup label, X3 tool bridge, X4 memory, X12 cascade engine, X13 weather by voice (branch, not yet merged), Playwright e2e.

**Claude Code (frontend), in order:**
1. Merge X13 PR.
2. F4 live timeline, trim display, tool chips, confirm card against real events.
3. F5 onboarding (4 steps).
4. F6 memory panel and Toast.
5. F7 skills panel and settings with Models section.
6. F8 accessibility and polish pass.
7. Week 4: bug fixes, README, screenshots.

**Codex (backend/eval):** X2, X1, X10, X11, X6, X5, X8, X7, X9 as queued above.

**You (human):** Nebius H100 and Token Factory key, Tavily key, spending limits, rotate leaked keys, enable GitHub secret scanning, fill `SECURITY.md` email, confirm AgentRouter/Nararouter/ExperimentalLab base URLs, record the demo video, submit on Devpost.
