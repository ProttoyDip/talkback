# TalkBack — Design

| | |
|---|---|
| **Status** | Draft v1 · 2 October 2026 |
| **Related docs** | [prd.md](prd.md) · [architecture.md](architecture.md) · [SECURITY.md](../SECURITY.md) |

This is the design source of truth for TalkBack. Claude Code must read it before building or changing any UI. The judges score **Design** as "a complete, coherent product experience, not just a technical proof of concept", so every screen in section 5 must exist and feel finished.

---

## 1. Design principles

1. **Conversation first.** The screen is a quiet stage for a voice conversation. Nothing competes with the two voices.
2. **Show the turn-taking.** Users should *see* full-duplex: who is speaking, the overlap, the moment of interruption, and what was actually heard.
3. **Calm, not flashy.** Motion explains state changes. It never decorates.
4. **Control is visible.** Microphone state, memory and tool access are always one click away and always honest.
5. **Readable everywhere.** Live captions, high contrast and keyboard control are core features, not extras.

## 2. Visual direction

**One-line direction:** *a dark recording studio at night — ink background, two signal colors, precise monospaced labels.*

- **Ink, not black.** A near-black blue-grey ground keeps contrast high without harsh pure black.
- **Two voices, two colors.** Warm orange is always the user. Teal is always TalkBack. These colors never mean anything else.
- **Studio labels.** Small uppercase monospaced labels (like channel names on a mixing desk) mark lanes, states and tools.
- **Flat surfaces.** Thin 1 px borders and slightly raised panels. No glass, no glows, no gradient washes.

This continues the look of the cover image and gallery images in `docs/images/`.

## 3. Design tokens

Define these once in `frontend/src/styles/tokens.css` as CSS custom properties and map them into the Tailwind theme. Never hard-code a color, size or duration in a component.

### 3.1 Color (dark, default)

| Token | Value | Use | Contrast on `--bg` |
|---|---|---|---|
| `--bg` | `#0D1014` | App background | — |
| `--surface` | `#14181D` | Panels, cards | — |
| `--surface-raised` | `#1B2027` | Popovers, menus | — |
| `--border` | `#2A3038` | 1 px borders, dividers | — |
| `--text` | `#F3F1EC` | Primary text | 17:1 |
| `--text-muted` | `#A7ADB5` | Secondary text | 8.6:1 |
| `--text-subtle` | `#7D848D` | Captions, timestamps (14 px+) | 5.0:1 |
| `--voice-user` | `#FF9A52` | User lane, user waveform | 9:1 |
| `--voice-assistant` | `#3ED6C4` | TalkBack lane, primary actions | 10:1 |
| `--voice-assistant-dim` | `#3ED6C4` at 45% opacity | Unheard words, past audio | — |
| `--danger` | `#FF7070` | Errors, "forget everything" | 6.5:1 |
| `--warning` | `#F2C94C` | Confirmation requests | 12:1 |
| `--focus` | `#F3F1EC` | 2 px focus ring, 2 px offset | — |

Text on `--voice-assistant` fills (primary buttons) uses `--bg`, never white.

A light theme is optional (P2). If built, keep the same two voice hues, darkened until text contrast is at least 4.5:1 on white.

### 3.2 Typography

| Role | Font | Size / line height | Weight |
|---|---|---|---|
| Display (onboarding hero) | Bricolage Grotesque | 64 / 68 | 800 |
| H1 | Bricolage Grotesque | 32 / 38 | 800 |
| H2 | Bricolage Grotesque | 22 / 28 | 700 |
| Body | Hanken Grotesk | 16 / 24 | 400 |
| Transcript | Hanken Grotesk | 18 / 28 | 400 |
| Label (uppercase, +0.08em tracking) | JetBrains Mono | 12 / 16 | 500 |
| Data (latency, timers) | JetBrains Mono | 14 / 20 | 500, tabular numbers |

Load from Google Fonts with `display=swap`. Never use Inter, Roboto or Arial.

### 3.3 Space, radius, elevation

- **Spacing scale (px):** 4, 8, 12, 16, 24, 32, 48, 64. Use only these.
- **Radius:** 8 (inputs, chips), 14 (cards), 20 (main panels), 999 (pills, mic button).
- **Elevation:** borders, not shadows. The only shadow is on popovers: `0 8px 24px rgba(0,0,0,0.4)`.

### 3.4 Motion

| Token | Value | Use |
|---|---|---|
| `--dur-instant` | 80 ms | Button press |
| `--dur-fast` | 150 ms | State color changes, flush on interruption |
| `--dur-base` | 240 ms | Panels, toasts |
| `--dur-slow` | 400 ms | Onboarding transitions |
| `--ease-out` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | Things entering |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | Things leaving |

Rules:
- Waveform bars follow real audio levels (from the AudioWorklet), never a looping fake animation.
- An interruption is shown in 150 ms or less: the assistant lane drops, a short marker appears on the timeline, and unheard words fade to `--voice-assistant-dim`.
- Respect `prefers-reduced-motion`: replace movement with instant state changes and opacity fades.
- Use the `motion` library (`import { motion } from "motion/react"`) for component animation. Animate only `transform` and `opacity`.

## 4. Layout

- **Desktop (≥ 1024 px):** three areas. Left rail (64 px icons: Conversation, Memory, Skills, Settings). Center stage (conversation). Right drawer (360 px, collapsible) for Memory or Skills.
- **Tablet (640–1023 px):** rail becomes a bottom tab bar; drawer becomes a full-height sheet.
- **Mobile (< 640 px):** single column; the mic button stays fixed at the bottom center with a 72 px touch target.
- Center stage max width: 880 px.

## 5. Screens

### 5.1 Onboarding (first run)
1. **Welcome:** display headline "Talk to me like a person." with a short line: "Interrupt me any time. I'll keep up." One primary button: "Allow microphone".
2. **Microphone permission:** explain why before the browser prompt. If denied, show how to re-enable it, with the browser name.
3. **Privacy promise:** three short lines: memory stays on your device, no recordings are kept, you can delete everything. Button: "Start talking".
4. **Headphones tip:** "Use headphones for the best interruptions." Dismissible.

### 5.2 Conversation (main screen)
From top to bottom:
- **Status bar:** connection dot + state label in mono ("LISTENING", "TALKBACK SPEAKING", "YOU INTERRUPTED", "CHECKING WEATHER"), latency readout in debug mode.
- **Duplex timeline:** two horizontal lanes, YOU (orange) and TALKBACK (teal), showing the last ~10 seconds as live level bars. Overlap regions are visible because both lanes are active at once. Interruptions leave a small white tick mark labeled "interrupt".
- **Transcript:** chat-like list, but without bubbles. Each turn has a mono speaker label and the text. After an interruption, the words TalkBack did not get to say stay visible but faded and struck through lightly, with a tooltip "Not spoken: you interrupted here". This is the signature detail of the product.
- **Tool chips:** inline under a TalkBack turn: "Searching the web…" → "3 sources" (expandable list of links).
- **Confirmation card:** when a sensitive action needs approval, a warning-colored card with the action summary and two buttons: "Yes, do it" and "No". Voice answers work too.
- **Mic control:** large round button bottom center. States: off, live (teal ring pulses with input level), muted (crossed icon). `Space` toggles mute.

### 5.3 Memory panel
- Search field, then a list of memory cards: text, kind label (PREFERENCE / FACT / REMINDER), when it was saved, and the exact words that created it ("You said: 'I like short answers'").
- Actions per card: edit, delete. Panel footer: "Forget everything" (danger, with confirmation).
- Empty state: "Nothing remembered yet. Try: 'Remember that I prefer Celsius.'"

### 5.4 Skills panel
- Cards for each skill: name, trigger phrases as mono chips, allowed tools as small icons, and a "Run" button.
- Running a skill shows step progress inline in the conversation.

### 5.5 Settings
- Tools: a toggle per tool (Web search, Weather) with what it can access.
- Privacy: "Save recordings on this device" (off by default), "Show transcripts in logs" (off).
- Voice: input device picker, a live mic level meter, and a sensitivity slider for interruptions.
- About: model names, Nebius region, version, link to the repo.

### 5.6 Error and offline states
| Situation | Message (plain, specific, with a next step) |
|---|---|
| Mic blocked | "Microphone is blocked. Click the camera icon in the address bar and allow access." |
| Voice engine offline | "The voice engine isn't reachable. Retrying in 5 seconds…" + "Retry now" |
| Network lost | "Connection lost. Reconnecting… your transcript is safe." |
| Tool failed | TalkBack says it out loud and the chip shows "Couldn't reach weather service". |

## 6. Conversation states

| State | Status label | Timeline | Mic button |
|---|---|---|---|
| `idle` | READY | Flat lanes | Teal ring, still |
| `listening` | LISTENING | User lane live | Ring follows input level |
| `assistant_speaking` | TALKBACK SPEAKING | Assistant lane live | Ring still |
| `overlap` | BOTH SPEAKING | Both lanes live | Ring follows input |
| `interrupted` | YOU INTERRUPTED | Assistant lane drops, tick mark | — |
| `thinking` / `tool` | CHECKING [TOOL] | Assistant lane low shimmer | — |
| `confirm` | NEEDS YOUR OK | Paused | — |
| `muted` | MUTED | User lane hidden | Crossed icon |
| `offline` | OFFLINE | Lanes grey | Disabled |

## 7. Accessibility (WCAG 2.2 AA)

- **Captions always available:** the transcript is the caption track; it streams in real time.
- **Screen readers:** status label in an `aria-live="polite"` region; confirmations in `aria-live="assertive"`. Waveforms are `aria-hidden` with a text equivalent in the status label.
- **Keyboard:** everything reachable by Tab, visible 2 px focus ring. `Space` mute, `Esc` stop TalkBack speaking, `M` memory, `K` skills.
- **Contrast:** text 4.5:1 minimum (3:1 for text 24 px and larger); color is never the only signal (labels accompany the two voice colors).
- **Targets:** at least 44 × 44 px; the mic button is 72 px.
- **Motion:** honor `prefers-reduced-motion`.

## 8. Voice and copy

- **Tone:** friendly, brief, direct. Short sentences. No exclamation marks except greetings.
- **Spoken answers:** under 20 seconds by default; offer more ("Want the details?").
- **UI copy:** sentence case, plain words, no jargon ("voice engine", not "inference server").
- **Never** claim things the product doesn't do ("I'll remember this forever" → "I'll remember this until you delete it").

## 9. Anti-slop rules

These patterns make an interface look AI-generated. Do not use them:
- Purple-to-blue gradients, gradient text, gradient blobs, glowing orbs.
- Glassmorphism panels and heavy drop shadows.
- Emoji as icons; generic sparkle (✨) "AI" icons.
- Cards with a thick colored left border.
- Centered hero + three feature cards + testimonial layouts.
- Inter, Roboto or Arial; default Tailwind gray palette; default shadcn look with no changes.
- Fake data: invented stats, fake user counts, lorem ipsum.
- Decorative looping animations that don't reflect real state.

Instead: real audio data, the two-voice color system, mono labels, generous spacing, and one signature detail (the faded "unheard" words).

## 10. How Claude Code should build the UI

Follow this order for every screen or component.

1. **Read this file and `tokens.css` first.** Use only the tokens.
2. **Use design skills when available.** Run the UI/UX skill (for example UI/UX Pro Max) to check layout, hierarchy and UX patterns; run the anti-AI-slop skill against section 9; run the taste or polish skill as a final pass on spacing, alignment and typography.
3. **Use 21st.dev MCP for components, then adapt them.** Search 21st.dev for a base component (e.g. "audio waveform", "toggle settings list", "command menu"). Treat results as a starting point: replace colors, fonts, radius and spacing with our tokens, remove gradients and shadows, and keep the accessible markup. Never paste a component unchanged.
4. **Animate with the `motion` library in code.** Note: the **Motion MCP server** connected to Claude Code creates *videos*, not in-app animation. Use it for the demo video or the README hero clip, not for UI motion.
5. **Build all states.** Every component must handle loading, empty, error, disabled and reduced-motion states from section 5 and 6.
6. **Check before finishing:** keyboard pass, contrast check, 375 px mobile check, reduced-motion check, and a visual comparison with the cover image style.

## 11. Component inventory

| Component | Notes |
|---|---|
| `DuplexTimeline` | Two lanes, canvas-rendered bars from real levels, interrupt tick marks |
| `MicButton` | 72 px, three states, input-level ring |
| `StatusBar` | Mono state label, connection dot, debug latency |
| `TranscriptTurn` | Speaker label, text, heard/unheard spans, tool chips |
| `ToolChip` | Running / done / failed; expandable sources |
| `ConfirmCard` | Warning color, summary, Yes/No, voice-answerable |
| `MemoryCard` | Text, kind label, origin quote, edit/delete |
| `SkillCard` | Name, trigger chips, tool icons, Run |
| `Toast` | "Remembered: …" with Undo, 4 s |
| `NavRail` / `TabBar` | Responsive navigation |
| `SettingsToggleRow` | Label, description, switch |

## References

- Hackathon judging criteria: https://nebiusglobalaihackathon.devpost.com/
- 21st.dev MCP: https://github.com/21st-dev/magic-mcp
- UI/UX Pro Max skill: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
