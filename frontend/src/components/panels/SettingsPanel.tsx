import { useState } from 'react'
import { api } from '../../api/client'
import type { SettingsUpdate, SettingsView } from '../../api/types'
import { useResource } from '../../api/useResource'
import type { ConversationModel } from '../../session/model'
import { PROVIDER_NAMES, type ModelRole, type ToolName } from '../../session/protocol'
import { Icon } from '../Icon'
import { SettingsToggleRow } from '../SettingsToggleRow'
import { ChoiceRow } from './ChoiceRow'
import { setEffects, useEffectsSetting } from '../../background/effects'
import { VoiceSection } from './VoiceSection'
import { ResourceView, SectionTitle } from './shared'
import { TOOL_LABEL } from './toolLabels'

/** Default and current value side by side, so "off by default" never reads as "off now". */
const onOff = (now: boolean) => `Default: off · Now: ${now ? 'on' : 'off'}`

const ROLE_TITLE: Record<ModelRole, string> = { voice: 'Voice', planner: 'Planner', search: 'Search' }

/** Kept in this browser only (src/background/effects.ts). */
function VisualEffects() {
  const effects = useEffectsSetting()
  return (
    <section aria-label="On this device">
      <SectionTitle>On this device</SectionTitle>
      <SettingsToggleRow
        label="Animated background"
        description="The moving field behind the app. Turn it off on slower laptops or to save battery."
        checked={effects.background}
        onChange={(background) => setEffects({ background })}
      />
      <SettingsToggleRow
        label="Push to talk"
        description="The microphone stays muted until you hold Space or the mic button. Good for noisy rooms."
        checked={effects.pushToTalk}
        onChange={(pushToTalk) => setEffects({ pushToTalk })}
      />
      <SettingsToggleRow
        label="Orb motion"
        description="The orb pulses while you and TalkBack speak. Off: it stays still."
        checked={effects.orbMotion}
        onChange={(orbMotion) => setEffects({ orbMotion })}
      />
    </section>
  )
}

export function SettingsPanel({ active }: { active: ConversationModel['models'] }) {
  const effects = useEffectsSetting()
  const { state, reload, set } = useResource(() => api.getSettings(), 'settings')
  const [failed, setFailed] = useState(false)

  const update = async (patch: SettingsUpdate) => {
    try {
      set(await api.updateSettings(patch))
      setFailed(false)
    } catch {
      setFailed(true)
    }
  }

  return (
    <ResourceView state={state} onRetry={reload}>
      {(settings: SettingsView) => (
        <div className="flex flex-col gap-8">
          {failed && (
            <p role="alert" className="text-data text-danger">
              That change was not saved. Try again.
            </p>
          )}

          <section aria-label="Tools">
            <SectionTitle>Tools</SectionTitle>
            {Object.entries(settings.tools).map(([name, tool]) => (
              <SettingsToggleRow
                key={name}
                label={TOOL_LABEL[name as ToolName]?.label ?? name}
                description={tool.description}
                checked={tool.enabled}
                onChange={(enabled) => void update({ tools: { [name]: enabled } })}
              />
            ))}
          </section>

          <section aria-label="Privacy">
            <SectionTitle>Privacy</SectionTitle>
            <SettingsToggleRow
              label="Save recordings on this device"
              description="Keeps up to 15 minutes of your own voice in this browser while the mic is on, so you can download it from the top bar. Never uploaded. Starts with the next conversation."
              status={onOff(effects.saveRecordings)}
              checked={effects.saveRecordings}
              onChange={(saveRecordings) => setEffects({ saveRecordings })}
            />
            <SettingsToggleRow
              label="Show transcripts in logs"
              description="Server logs include what you and TalkBack say. For local debugging: it works only on a server that allows it."
              status={onOff(settings.transcripts_in_logs)}
              checked={settings.transcripts_in_logs}
              onChange={(transcripts_in_logs) => void update({ transcripts_in_logs })}
            />
          </section>

          <section aria-label="Conversation">
            <SectionTitle>Conversation</SectionTitle>
            <ChoiceRow
              label="Interruptions"
              description="How quickly your voice stops TalkBack. Use Low in noisy rooms or without headphones."
              value={settings.interrupt_sensitivity}
              options={[
                { value: 'low', label: 'Low' },
                { value: 'normal', label: 'Normal' },
                { value: 'high', label: 'High' },
              ]}
              onChange={(interrupt_sensitivity) => void update({ interrupt_sensitivity })}
            />
            <ChoiceRow
              label="Answer length"
              value={settings.answer_length}
              options={[
                { value: 'short', label: 'Short' },
                { value: 'normal', label: 'Normal' },
                { value: 'detailed', label: 'Detailed' },
              ]}
              onChange={(answer_length) => void update({ answer_length })}
            />
            <p className="mt-1 text-data text-text-muted">Changes apply to the next conversation.</p>
          </section>

          <VoiceSection />

          <VisualEffects />

          <section aria-label="Models">
            <SectionTitle>Models</SectionTitle>
            <p className="text-body text-text-muted">Running now</p>
            <p className="mb-1 text-body text-text">
              {active.voice
                ? `${active.voice.model} via ${PROVIDER_NAMES[active.voice.provider]}`
                : settings.models.voice_model}
            </p>
            <p className="mb-4 text-data text-text-muted">
              {settings.models.full_duplex
                ? 'Full-duplex: on. TalkBack listens and talks at the same time.'
                : 'Full-duplex: off. TalkBack stops talking when it hears you talk over it.'}
            </p>

            <details className="group">
              <summary className="flex min-h-target cursor-pointer list-none items-center justify-between gap-2 text-body font-medium text-text">
                Advanced: models and providers
                <Icon name="chevron" className="size-4 transition-transform duration-(--dur-fast) group-open:rotate-180" />
              </summary>
              <dl className="mb-4 mt-2 flex flex-col gap-2 text-body">
                {(['voice', 'planner', 'search'] as const).map((role) => {
                  const current = active[role]
                  return (
                    <div key={role} className="flex flex-wrap justify-between gap-x-4">
                      <dt className="text-text-muted">{ROLE_TITLE[role]}</dt>
                      <dd className="text-text">
                        {current
                          ? `${current.model} via ${PROVIDER_NAMES[current.provider]}${current.backup ? ' (backup)' : ''}`
                          : role === 'voice'
                            ? settings.models.voice_model
                            : 'Not used yet'}
                      </dd>
                    </div>
                  )
                })}
              </dl>

              <label htmlFor="planner-model" className="mb-1 block text-body font-medium text-text">
                Planner model
              </label>
              <select
                id="planner-model"
                value={settings.models.planner_model}
                onChange={(e) => void update({ planner_model: e.target.value })}
                className="min-h-target w-full rounded-input border border-border bg-bg px-3 text-body text-text"
              >
                {settings.models.planner_options.map((option) => (
                  <option key={option.id} value={option.id} disabled={!option.available}>
                    {option.model}
                    {option.nvidia ? ' · NVIDIA' : ''}
                    {option.available ? '' : ' (not set up)'}
                  </option>
                ))}
              </select>

              <p className="mb-1 mt-4 text-data text-text-muted">
                Backups receive your words only if the main provider fails. Turn off any you do not want.
              </p>
              {settings.models.providers
                .filter((provider) => !provider.primary)
                .map((provider) => (
                  <SettingsToggleRow
                    key={`${provider.role}-${provider.id}`}
                    label={provider.name}
                    description={`${ROLE_TITLE[provider.role]} backup${provider.configured ? '' : ' · no key set up'}`}
                    checked={provider.enabled}
                    disabled={!provider.configured}
                    onChange={(enabled) => void update({ providers: { [provider.id]: enabled } })}
                  />
                ))}
            </details>
          </section>

          <section aria-label="About">
            <SectionTitle>About</SectionTitle>
            <a
              href="https://github.com/ProttoyDip/talkback"
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block min-h-target py-2 text-body text-voice-assistant underline underline-offset-4"
            >
              Source code on GitHub
            </a>
          </section>
        </div>
      )}
    </ResourceView>
  )
}
