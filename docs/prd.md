# TalkBack — Product Requirements Document

| | |
|---|---|
| **Product** | TalkBack: a private, full-duplex voice assistant you can interrupt |
| **Event** | Nebius x NVIDIA Global AI Hackathon 2026 |
| **Track** | Personal AI |
| **Deadline** | 30 October 2026, 10:00 AM PDT |
| **Status** | Draft v1 · 2 October 2026 |
| **Related docs** | [architecture.md](architecture.md) · [design.md](design.md) · [SECURITY.md](../SECURITY.md) |

---

## 1. Summary

Voice assistants still force strict turn-taking. You speak, you wait, and you cannot correct them mid-answer. TalkBack is a voice-first personal assistant that listens while it talks. You can interrupt it, it remembers what you actually heard, and it continues from your correction. It also remembers you across sessions, runs reusable skills (like a morning brief), and keeps your data under your control.

It runs on an open NVIDIA full-duplex speech model hosted on Nebius AI Cloud, with NVIDIA Nemotron on Nebius Token Factory for reasoning and tool planning.

## 2. Problem

- **Turn-taking is unnatural.** People interrupt, give quick feedback ("mm-hm"), and change their minds mid-sentence. Most assistants ignore speech while they talk, so users must wait or press a button.
- **Interruptions break context.** When cascaded assistants are cut off, they usually forget what they had already said, or assume the user heard the full answer.
- **Personal assistants leak control.** Most voice assistants store audio and memory on servers the user cannot inspect or delete.

## 3. Hackathon fit

### 3.1 Mandatory rules

| Requirement | How TalkBack meets it |
|---|---|
| Runs on Nebius Token Factory or Nebius AI Cloud | Voice model on a Nebius AI Cloud H100; Nemotron via Token Factory |
| Uses at least one NVIDIA open-source model | NVIDIA NemotronLabs VoiceChat 11B and NVIDIA Nemotron 3 Nano |
| Public repo with MIT / Apache 2.0 / MPL 2.0 license visible | MIT license in the repo root |
| README with setup and clear Nemotron / Token Factory guidance | README has a dedicated "Using NVIDIA models on Nebius" section |
| Public YouTube demo, 3 minutes or less | Scripted demo, see section 11 |

### 3.2 Personal AI track requirements

The track asks for an always-on, private assistant that works for the user while keeping their data under their control, with:

| Track requirement | TalkBack feature | Priority |
|---|---|---|
| Persistent memory | Local memory store with a visible, editable Memory panel | P0 |
| Reusable skills | Skills defined as small YAML files (e.g. "morning brief") | P0 |
| Access to user-selected tools and information | User turns each tool on or off in Settings | P0 |
| Task execution across daily workflows | Skills chain tools: weather + search + reminders | P1 |
| Data under the user's control | Memory stored locally, no audio stored by default, one-click "forget everything" | P0 |
| Suggested tools (NemoClaw, OpenShell, Hermes Agent, Nebius Serverless) | Optional: run tool execution inside an OpenShell sandbox; voice model can run as a Nebius Serverless endpoint | P2 |

### 3.3 Judging criteria

| Criterion | What judges look for | Our answer |
|---|---|---|
| Technological implementation | Strong use of Nebius and Nemotron | Two NVIDIA models with distinct roles, measured latency, a clear tool-call bridge |
| Design | A complete, coherent product, not only a proof of concept | A polished conversation screen, Memory and Skills panels, and onboarding |
| Potential impact | A real problem for real users | Natural voice access for hands-busy, low-vision and older users |
| Quality of the idea | Creative, non-obvious use of the models | Interruption-aware memory: the assistant knows exactly what you heard |

## 4. Users

| Persona | Need | Example |
|---|---|---|
| **Busy professional** (primary) | Hands-free help while cooking, commuting or working | "What's my weather? …no, for tomorrow." |
| **Low-vision user** | Full control by voice, with fast correction | Interrupts a long answer to ask for the short version |
| **Older adult** | Natural conversation without learning commands | Says "mm-hm" and expects the assistant to keep going |
| **Hackathon judge** (demo audience) | Understands the value within 3 minutes | Watches an interruption handled live |

## 5. Goals and non-goals

### Goals
1. A natural, interruptible voice conversation with a median response latency under 500 ms.
2. Correct handling of at least 90% of interruptions in a scripted test set.
3. Persistent personal memory and reusable skills the user can see and control.
4. A design polished enough to feel like a product, not a demo.

### Non-goals (for the hackathon)
- Languages other than English (the voice model is English-only).
- Phone-call integration, smart-home control, or native mobile apps.
- Multi-user accounts or a hosted public service.
- Training or fine-tuning models.

## 6. User stories

| ID | As a… | I want to… | So that… | Priority |
|---|---|---|---|---|
| US-1 | user | talk to TalkBack in the browser and hear it reply in real time | I can use it hands-free | P0 |
| US-2 | user | interrupt it at any moment | I don't wait for answers I don't need | P0 |
| US-3 | user | say "mm-hm" or "okay" without stopping it | it feels like a real conversation | P0 |
| US-4 | user | ask for live information (web, weather) | I get current answers | P0 |
| US-5 | user | have it remember my preferences across sessions | I don't repeat myself | P0 |
| US-6 | user | see, edit and delete what it remembers | I stay in control of my data | P0 |
| US-7 | user | run a skill like "morning brief" with one phrase | I automate my daily routine | P0 |
| US-8 | user | confirm before it does anything sensitive | it can't act against my wishes | P0 |
| US-9 | user | read a live transcript with captions | I can follow along, even in noise | P1 |
| US-10 | user | turn tools on or off | I choose what it can access | P1 |
| US-11 | user | create my own skill | I can extend it | P2 |

## 7. Functional requirements

### 7.1 Conversation (P0)
- **FR-1** Stream microphone audio to the backend as 16 kHz mono PCM in 20 ms frames.
- **FR-2** Play assistant audio (22.05 kHz) as it streams, with no full-sentence buffering.
- **FR-3** Detect user speech while the assistant is speaking.
- **FR-4** Treat speech as an interruption only if it lasts at least 250 ms and is not a backchannel ("mm-hm", "yeah", "okay", "right").
- **FR-5** On interruption: stop playback within 150 ms of detection, report the playback position, and trim the assistant's last message to the words actually played.
- **FR-6** Show a live, two-lane waveform (user and assistant) and a transcript.

### 7.2 Tools (P0)
- **FR-7** Bridge the voice model's tool-call output to real tools and return results to it.
- **FR-8** Built-in tools: web search (Tavily), weather (Open-Meteo), memory read/write, skill runner.
- **FR-9** Speak a short filler ("Let me check that") if a tool takes longer than 700 ms.
- **FR-10** Send multi-step or complex requests to Nemotron on Token Factory for planning.

### 7.3 Memory (P0)
- **FR-11** Store memories locally (SQLite) with a source, time and confidence for each item.
- **FR-12** Only the user's own words can create a memory. Web results and tool outputs never write memory directly.
- **FR-13** Memory panel: list, search, edit, delete, and "forget everything".
- **FR-14** Say out loud when something new is remembered ("I'll remember you prefer Celsius").

### 7.4 Skills (P0)
- **FR-15** Skills are YAML files: a name, trigger phrases, allowed tools, and steps.
- **FR-16** Ship three skills: Morning brief, Quick research, Remind me.
- **FR-17** Skills panel lists skills, their allowed tools, and a "Run" button.

### 7.5 Privacy and control (P0)
- **FR-18** No raw audio stored by default. An opt-in "Save recordings" setting stores them locally only.
- **FR-19** A visible microphone state at all times, and one-click mute.
- **FR-20** Sensitive actions require spoken or on-screen confirmation (see SECURITY.md).

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| Latency | Median end-of-speech to first audio under 500 ms; p95 under 900 ms |
| Interruption | Playback stops within 150 ms of a confirmed interruption |
| Accuracy | At least 90% correct interruption handling over 50 scripted conversations |
| Availability | Demo must run reliably for a 3-minute recording; graceful reconnect on network drops |
| Browsers | Latest Chrome and Edge (primary), Firefox and Safari (best effort) |
| Accessibility | WCAG 2.2 AA: captions, keyboard control, screen reader support, 4.5:1 text contrast |
| Privacy | All memory local; API keys only on the server; no third-party analytics |
| Cost | GPU runs only during development and demo; stop the instance when idle |

## 9. Success metrics

| Metric | Target | How measured |
|---|---|---|
| Median response latency | < 500 ms | `eval/latency.py` timestamps |
| p95 response latency | < 900 ms | same |
| Interruption handled correctly | ≥ 90% | `eval/interruptions.py`, 50 scripted conversations |
| Backchannel false-stop rate | ≤ 10% | same test set |
| Tool-call success rate | ≥ 95% | eval logs |
| Demo completeness | All 4 features shown in under 3 minutes | video review |

## 10. Milestones (4 weeks)

| Week | Dates | Deliverable |
|---|---|---|
| 1 | 2–8 Oct | Voice model running on Nebius; browser audio loop end to end; first latency number |
| 2 | 9–15 Oct | Interruption logic, backchannels, transcript trimming; tool bridge with web and weather |
| 3 | 16–22 Oct | Memory, skills, Nemotron planner, full UI polish, accessibility pass |
| 4 | 23–30 Oct | Evaluation runs, README, demo video, Devpost submission (submit by 29 Oct to keep a buffer) |

## 11. Demo script (3 minutes)

1. **0:00–0:20** The problem: a normal assistant that can't be interrupted.
2. **0:20–1:30** Live: ask for the weather, interrupt with "no, tomorrow", say "mm-hm" to show it continues, ask a web question while it keeps talking.
3. **1:30–2:00** Memory and skills: "Remember I like short answers", then run "morning brief".
4. **2:00–2:30** How it's built: architecture image, Nebius console, Token Factory calls.
5. **2:30–3:00** Measured results and what's next.

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| GPU cost or availability on Nebius | Cannot run the voice model | Apply for hackathon credits early; stop the VM when idle; record the demo early |
| Voice model setup takes longer than planned | Week 1 slips | Fallback: cascaded pipeline (streaming ASR → Nemotron → TTS) with the same UI and interruption logic |
| Echo causes false interruptions | Poor demo | Browser echo cancellation, headphones in the demo, raised threshold while the assistant speaks |
| Tool-call format differs from documentation | Tools fail | Build the bridge against recorded model output first |
| Prompt injection via web results | Unsafe actions | See SECURITY.md: results treated as data, confirmations for sensitive actions |

## 13. Open questions

- Is NemotronLabs VoiceChat available as a ready container, or must we build from the NVIDIA Speech repo? (Resolve in week 1.)
- Does the hackathon provide Nebius GPU credits, and how many hours?
- Should the voice model run on a dedicated VM or a Nebius Serverless endpoint? (See architecture.md, ADR-2.)

## References

- Hackathon rules and judging criteria: https://nebiusglobalaihackathon.devpost.com/
- NVIDIA NemotronLabs VoiceChat 11B: https://huggingface.co/nvidia/NVIDIA-NemotronLabs-VoiceChat-11B
- Nebius Token Factory: https://docs.tokenfactory.nebius.com/switch
