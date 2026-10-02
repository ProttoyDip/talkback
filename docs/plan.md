# TalkBack — Build plan (two agents)

| | |
|---|---|
| **Status** | v1 · 2 October 2026 |
| **Deadline** | Submit by 29 October 2026 (Devpost closes 30 October, 10:00 AM PDT) |
| **Related docs** | [prd.md](prd.md) · [architecture.md](architecture.md) · [design.md](design.md) · [SECURITY.md](../SECURITY.md) |

Two coding agents build TalkBack at the same time: **Claude Code** and **Codex**. This plan says who owns what, how they avoid conflicts, and in what order the work happens.

---

## 1. Current state (2 October)

| Part | State |
|---|---|
| Docs, README, LICENSE, cover image | Done |
| Frontend: Conversation screen layout, design tokens | Done, static example data only |
| Backend: `/health`, session tokens, `/ws/session` gateway, 29 tests | Done, not connected to any model |
| Secret scan on every push (gitleaks workflow) | Done |
| Audio, voice model, interruption logic, tools, memory, skills, other screens, evaluation | Not started |

## 2. How the work is split

The split is **by folder**. Each agent only edits files it owns. This removes merge conflicts.

| Owner | Owns | Main job |
|---|---|---|
| **Claude Code** | `frontend/` | Everything the user sees and hears in the browser |
| **Codex** | `backend/`, `eval/` | Everything on the server: model, turn-taking, tools, memory, skills, measurement |
| **Shared (contract)** | `backend/app/protocol.py`, `docs/architecture.md` §3, this file | Changed only through a "contract" pull request (section 4) |
| **You (human)** | Accounts, keys, GPU, video, submission | See section 7 |

Other files: `README.md` is updated by whoever finishes a feature, in a small separate commit. `docs/prd.md` and `docs/design.md` change only when you ask.

## 3. Branches and merging

- Claude Code works on branches named `claude/<task>`. Codex works on `codex/<task>`.
- Never commit directly to `main`. Open a pull request; merge after tests pass.
- Before opening a pull request: `git fetch origin && git rebase origin/main`, then run the tests:
  - backend: `cd backend && .venv/bin/python -m pytest` (Windows: `.venv\Scripts\python -m pytest`)
  - frontend: `cd frontend && npm run build && npm run lint`
- If both agents run on the same computer, use separate folders: `git worktree add ../talkback-codex codex/<task>`.
- Small pull requests (one task each). Merge often, at least once a day.

## 4. Contract first (Phase 0)

Both sides talk only through the session protocol (WebSocket) and a small REST API. These must be agreed **before** parallel work starts, so neither side waits for the other.

**Rule:** a contract change is its own pull request that edits `backend/app/protocol.py` and `docs/architecture.md` §3 together. The other agent reviews it. No other code in that pull request.

### Phase 0 tasks (Claude Code, before the split): done

| ID | Change | Why |
|---|---|---|
| C0.1 | Add `message_id` to `transcript.delta` | `transcript.trim` refers to a message, but deltas have no id |
| C0.2 | Add `error` event `{code, message}` (server → client) | The UI needs "voice engine offline", "tool failed" (design.md 5.6) |
| C0.3 | Add `session.end` event `{reason}` | Clean close for idle and time limits |
| C0.4 | Define REST for memory: `GET /api/memories?q=`, `PATCH /api/memories/{id}`, `DELETE /api/memories/{id}`, `DELETE /api/memories` | Memory panel (design.md 5.3) |
| C0.5 | Define REST for skills: `GET /api/skills`, `POST /api/skills/{id}/run` | Skills panel (design.md 5.4) |
| C0.6 | Define REST for settings: `GET /api/settings`, `PATCH /api/settings` (tool on/off, save recordings) | Settings (design.md 5.5), SECURITY.md T4 |
| C0.7 | Write `docs/fixtures/demo_session.jsonl`: a recorded list of server events for the demo conversation | Both sides test against the same data |

After Phase 0 merges, both agents start at the same time.

## 5. Work packages

Each package is one or more pull requests. "Needs" lists what must be merged first.

### Codex — backend and evaluation

| ID | Package | Needs | Done when |
|---|---|---|---|
| X1 | **Fake voice model** (`backend/app/fake_voice.py`): replays `demo_session.jsonl` with real timing, sends PCM audio chunks (a tone or silence is fine), transcript deltas and word timestamps | Phase 0 | A browser session receives a full scripted conversation; tests pass |
| X2 | **Turn-taking engine** (`turn_taking.py`): Silero VAD on 20 ms frames, 250 ms minimum speech, backchannel rule (< 600 ms + word list), `audio.flush`, trimming from `samples_played` to heard words, `transcript.trim` | X1 | Unit tests for VAD decisions and trimming math; interrupting the fake model trims correctly |
| X3 | **Tool bridge** (`tool_bridge.py`, `tools/`): `<TOOLCALL>` parser, JSON schema per tool, allowlist, 10 calls/minute, untrusted-data wrapping, 4 s timeout, filler after 700 ms, confirmation flow for `sensitive` tools. Tools: Tavily, Open-Meteo. Settings REST from C0.6 (tool on/off) | Phase 0 | All SECURITY.md section 6 tests for tools pass |
| X4 | **Memory** (`memory.py`, `tools/memory.py`): SQLite + FTS5, schema from architecture.md 7.1, writes only from `user_utterance`, REST from C0.4, `memory.saved` event | Phase 0 | "Web result says remember…" test creates no memory |
| X5 | **Skills** (`skills.py`, `skills/*.yaml`): loader, trigger matching, `allowed_tools` enforcement, 3 skills (Morning brief, Quick research, Remind me), REST from C0.5 | X3 | A skill cannot call a tool outside its list (test) |
| X6 | **Planner** (`planner.py`): Nemotron 3 Nano on Token Factory with the official `openai` client; fall back to no planning on error | X3, your `NEBIUS_API_KEY` | Multi-step request produces a step list; error path tested |
| X7 | **VoiceChat client** (`voice_client.py`): same interface as the fake model, connects to the real container over private network | X1, Nebius GPU (section 7) | Real conversation end to end on Nebius |
| X8 | **Evaluation** (`eval/latency.py`, `eval/interruptions.py`, 50 scripted conversations with pre-recorded user audio) | X2, then X7 for real numbers | Script prints median, p95, interruption accuracy, backchannel false-stop rate |
| X9 | **Deployment**: Nebius VM setup notes, HTTPS, serve built frontend, access code for a public demo (SECURITY.md T8) | X7 | Demo URL works over HTTPS |
| X10 | **LLM provider chain** (`providers.py`): one OpenAI-compatible client per provider, tried in order (section 8). Switch on auth, quota, rate-limit, server errors and timeouts; cool a failed provider down (longer for "out of credit"). Model allowlist per provider. Send `model.active` when the provider changes. Add `OPENROUTER_API_KEY`, `AGENTROUTER_API_KEY`, `NARAROUTER_API_KEY`, `EXPERIMENTALLAB_API_KEY`, `PERPLEXITY_API_KEY` (empty) to `.env.example`. The planner (X6) uses this chain | X6, C1 | Mocked tests for every switch reason; keys never logged |
| X11 | **Search fallback**: Tavily first, Perplexity search second, same result sanitizing as X3 | X3 | Mocked tests; Tavily failure switches to Perplexity |

### Claude Code — frontend

| ID | Package | Needs | Done when |
|---|---|---|---|
| F1 | **Session client and state machine** (`src/state/session.ts`): `POST /api/session`, WebSocket, typed events from the contract, reconnect, offline states. A local replay of `demo_session.jsonl` for development | Phase 0 | The Conversation screen runs from events, not static data |
| F2 | **Mic capture** (`src/audio/capture.worklet.ts`): `getUserMedia` with echo cancellation, resample to 16 kHz, 20 ms PCM16 frames, input level for the ring and timeline, mute | F1 | Frames reach the backend; mic ring follows the voice |
| F3 | **Playback** (`src/audio/playback.worklet.ts`): 22.05 kHz ring buffer, `samples_played` reports every 100 ms, instant flush on `audio.flush`, routing for echo cancellation (ADR-4) | F1 | Plays fake-model audio; flush stops within 150 ms |
| F4 | **Live timeline and transcript**: canvas lanes from real levels, interrupt ticks, unheard words from `transcript.trim`, tool chips from `tool.status`, confirm card from `tool.confirm_request` | F1–F3, X1 | Interrupting the fake model shows the trim live |
| F5 | **Onboarding** (design.md 5.1): welcome, mic permission with browser-specific help, privacy promise, headphones tip | none | All four steps, keyboard and 375 px checked |
| F6 | **Memory panel, Toast** (design.md 5.3, `Toast` from 11) | C0.4 | Works against X4, and against a mock until X4 lands |
| F7 | **Skills panel and Settings** (design.md 5.4, 5.5), including a **Models** section: the voice model (fixed), a planner model picker (allowlist only), the backup order with on/off per provider, and which provider is active now | C0.5, C0.6, C1 | Works against X5 and settings API |
| F9 | **Backup notice**: a small "Backup model" label in the status bar while a backup provider answers, so the user always knows which model is in use | C1 | Shows and clears on `model.active` |
| F8 | **Accessibility and polish pass**: keyboard, screen reader, contrast, reduced motion, 375 px, error states (design.md 5.6, 7) | F1–F7 | Checklist in design.md section 10 step 6 passes |

### Contract change C1 (Claude Code): done

| ID | Change |
|---|---|
| C1 | `SettingsView` gets `models`: the voice model (name, where it runs), the planner options (`id`, provider, model, `available` = key configured) and backup search. `SettingsUpdate` gets `planner_model` and per-provider on/off. New server event `model.active {role, provider, model, backup}`. Keys and base URLs never leave the server |

## 6. Timeline

| Week | Dates | Claude Code | Codex | Shared milestone |
|---|---|---|---|---|
| 1 | 2–8 Oct | Phase 0, F1, F2, F3 | X1, X3 | Browser talks to the fake model with real audio |
| 2 | 9–15 Oct | F4, F5, F6 | X2, X4, X7 (when GPU is ready) | Live interruption works end to end; first real latency number |
| 3 | 16–22 Oct | F7, F8 | X5, X6, X8 | Feature complete; evaluation runs |
| 4 | 23–29 Oct | Bug fixes, README, screenshots | X9, final eval numbers | Demo recorded; submit by 29 Oct |

If the real voice model is late, the demo still works on the fake model plus the PRD fallback (cascaded ASR → Nemotron → TTS, prd.md section 12). Decide by 15 October.

## 7. Human tasks (only you can do these)

| When | Task |
|---|---|
| Now | Apply for Nebius hackathon GPU credits; create a Nebius AI Cloud project |
| Now | Get API keys: Nebius Token Factory, Tavily. Put them only in `backend/.env` |
| Now | Send the base URL and model list (or docs link) for AgentRouter, Nararouter and ExperimentalLab. They are not used until this is confirmed (section 8) |
| Now | Set a spending limit on every provider account. The keys pasted in chat are in its history: rotate them if this history may be shared |
| Now | Turn on GitHub secret scanning and push protection (Settings → Code security) |
| Now | Replace `[YOUR SECURITY EMAIL]` in `SECURITY.md` |
| Week 1 | Start an H100 VM on Nebius; check how to run the VoiceChat container (prd.md 13) |
| Each day | Review and merge pull requests from both agents |
| Week 4 | Record the 3-minute demo video; upload to YouTube; submit on Devpost |

## 8. Model providers, backups and user choice

### 8.1 What each provider can do

| Role | Primary | Backups, in order | Notes |
|---|---|---|---|
| Voice (speech to speech) | NVIDIA NemotronLabs VoiceChat on a Nebius H100 | None | No backup provider hosts a full-duplex speech model. The fallback for voice is still the cascaded pipeline (prd.md 12) |
| Planner and summaries (text LLM) | Nemotron 3 Nano on Nebius Token Factory | OpenRouter (an NVIDIA Nemotron model first), then AgentRouter, Nararouter, ExperimentalLab | Backups only after their base URL and models are confirmed |
| Web search | Tavily | Perplexity search | Same sanitizing rules (SECURITY.md T1) |

### 8.2 Rules

- **Hackathon rule first.** The default is always Nebius Token Factory and Nebius AI Cloud with NVIDIA models. Backups are for development and outages only. Record the demo and the evaluation numbers on the primary.
- **Keys stay on the server**, only in `backend/.env` (SECURITY.md T6). The browser sees provider and model names, never keys or URLs.
- **When to switch:** authentication errors, "out of credit" (402), rate limits (429), server errors (5xx) and timeouts. A failed provider waits before it is tried again (a few minutes; much longer after 402).
- **Privacy is visible.** A backup provider receives the user's words. Settings lists every provider that may receive data, and the user can turn each backup off. With all backups off, a primary failure shows an error instead of switching.
- **Visible model.** The status bar shows "Backup model" while a backup answers; Settings shows which model is active and why.
- **User choice.** The user can pick the planner model from an allowlist kept on the server. NVIDIA models are listed first and marked as the default. The voice model cannot be changed.
- **Unknown providers** are added only after their documentation is checked: an OpenAI-compatible API, a clear data policy, exact model IDs pinned in the allowlist.

## 9. Rules for both agents

1. Read `docs/prd.md`, `docs/architecture.md`, `docs/design.md`, `SECURITY.md` and this file before starting.
2. Edit only the folders you own (section 2). If you need a change in the other side or in the contract, write it in the pull request description instead.
3. Follow every item in `SECURITY.md` section 5. No secrets in code, logs or commits.
4. Pin exact dependency versions. Add a dependency only when it is needed.
5. Every package comes with tests. Do not merge with failing tests.
6. Never describe a planned feature as working in the README.
7. Keep this file current: tick a package in section 5 when its pull request merges.
