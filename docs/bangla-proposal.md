# Bangla and mixed-language speech: findings and proposal

| | |
|---|---|
| **Status** | Proposal, 2 October 2026. No code changed. |
| **Decision needed** | Keep the hackathon demo English-only (recommended) or add a Bangla provider (section 4) |

## 1. What was checked (2 October, with the project's own keys)

| Layer | Result |
|---|---|
| Speech recognition (NVIDIA catalog) | One model: `parakeet-0.6b-en-US-asr-streaming`, **en-US only**. NVIDIA's docs list no Bangla model in Parakeet or Canary. |
| Speech output (Magpie Multilingual) | en-US, es-US, fr-FR, de-DE, zh-CN, vi-VN, it-IT, hi-IN, ja-JP, ko-KR, ar-AR, pt-BR. **No Bangla** (hi-IN is Hindi). |
| Text model, Bangla understanding | `nemotron-3-super-120b-a12b` understood a mixed Bangla–English question and answered in 6 s, but its Bangla output was **mixed with Hindi, Cyrillic and Latin words**. Not usable for spoken Bangla as is. `nemotron-3.5-lightning-30b-a3b` took 43 s (it reasons at length). One sample each: this is a smoke test, not an evaluation. |
| Nebius Token Factory | `NEBIUS_API_KEY` is not set here, so its model list and any recognizer there were **not checked**. |

## 2. Separate finding: Nemotron 3 Nano is retired on NVIDIA's own catalog

The NVIDIA catalog returns `410 Gone` for `nvidia/nemotron-3-nano-30b-a3b` ("end of life on 2026-09-01"). The project does not use that endpoint: it calls Nebius, then OpenRouter. OpenRouter still lists and serves the model (first word in about 3.7 s in a test on 2 October). Nebius could not be checked (no key here), so **check that Nebius still serves `nvidia/nvidia-nemotron-3-nano-30b-a3b` before relying on it as the primary.** NVIDIA's hosted `nemotron-3-super-120b-a12b` and `nemotron-3.5-lightning-30b-a3b` were too slow or unreliable on the free catalog (up to 79 s to the first word), so they are not good replacements for a voice reply path.

## 3. What the 16-feature list needs, by layer

| Need | Layer | Owner |
|---|---|---|
| Bangla and mixed recognition | New recognizer provider (section 4) | Codex |
| Bangla voice | New voice provider (section 4) | Codex |
| Filler words, self-correction, "is the thought finished" | Conversation controller before the model answers | Codex (extends X2) |
| Reactions ("hmm", "আচ্ছা", "হ্যাঁ") read in context | Controller keeps short sounds as events and passes them to the model with context | Codex (X2) |
| Language, speed and level preferences | Settings and memory (approved only) | Both |
| English-practice mode | A setting plus a prompt mode | Both |

## 4. Proposed contract change (its own "contract" pull request)

Proposal only. Field names are suggestions.

- `SettingsView` / `SettingsUpdate`: `language: "auto" | "en" | "bn"` (default `"en"`), `speaking_speed: 0.8..1.2`, `explanation_level: "simple" | "normal" | "detailed"`, `english_practice: bool` (default off).
- `ProviderInfo.role` adds `"speech_in"` and `"speech_out"`, so a Bangla recognizer or voice shows in Settings with `receives_user_words` and the same on/off switch as other backups. Audio leaves the server when one is used, so Settings must say so in plain words.
- `transcript.delta` gets optional `lang: "en" | "bn"` so the frontend can pick a Bangla-capable font for the caption.
- Server code: a `SpeechRecognizer` and a `SpeechSynthesizer` interface with the NVIDIA classes as the first implementation, so a Bangla provider is a new class, not a rewrite.

Frontend work after that (about a day): a language and speed section in Settings, a Bangla font in `tokens.css` (design.md 3.2 names none), and mixed-script caption checks.

## 5. Candidate Bangla providers (not yet verified)

Check each for streaming, Bangla and mixed-language accuracy, price and data policy before choosing:

- Recognition: a multilingual Whisper-class model (if Nebius or another provider hosts one), or a cloud recognizer with `bn-BD`.
- Voice: a cloud voice with a Bangla option (for example Google or Azure), or an open Bangla TTS model hosted on the Nebius GPU.

## 6. Recommendation

1. **Hackathon demo: English-only.** Add Bangla to the README roadmap as future work, and do not claim it in the submission.
2. Do the retired-model check (section 2) first. It affects the primary stack.
3. If time remains after X2, X8 and the demo, run the provider checks in section 5 and decide by 15 October (the same date as the voice-model decision in plan.md section 6).
4. Build the conversation controller (hesitation, patient turn-taking, reactions) now, in English. It is the largest quality gain and it needs no new provider.
