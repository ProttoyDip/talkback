import { useState } from 'react'
import { api } from '../../api/client'
import type { SettingsUpdate, SettingsView } from '../../api/types'
import { useResource } from '../../api/useResource'
import type { ConversationModel } from '../../session/model'
import { PROVIDER_NAMES, type ModelRole, type ToolName } from '../../session/protocol'
import { SettingsToggleRow } from '../SettingsToggleRow'
import { setEffects, useEffectsSetting } from '../../background/effects'
import { VoiceSection } from './VoiceSection'
import { ResourceView, SectionTitle } from './shared'

const TOOL_TITLE: Partial<Record<ToolName, string>> = {
  web_search: 'Web search',
  weather: 'Weather',
}

const ROLE_TITLE: Record<ModelRole, string> = { voice: 'Voice', planner: 'Planner', search: 'Search' }

/** Kept in this browser only (src/background/effects.ts). */
function VisualEffects() {
  const effects = useEffectsSetting()
  return (
    <section aria-label="Visual effects">
      <SectionTitle>Visual effects</SectionTitle>
      <SettingsToggleRow
        label="Animated background"
        description="The moving field behind the app. Turn it off on slower laptops or to save battery."
        checked={effects.background}
        onChange={(background) => setEffects({ background })}
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
                label={TOOL_TITLE[name as ToolName] ?? name}
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
              description="Off by default. Nothing is recorded unless you turn this on."
              checked={settings.save_recordings}
              onChange={(save_recordings) => void update({ save_recordings })}
            />
            <SettingsToggleRow
              label="Show transcripts in logs"
              description="Off by default. Logs then hold no words from your conversations."
              checked={settings.transcripts_in_logs}
              onChange={(transcripts_in_logs) => void update({ transcripts_in_logs })}
            />
          </section>

          <VoiceSection />

          <VisualEffects />

          <section aria-label="Models">
            <SectionTitle>Models</SectionTitle>
            <dl className="mb-4 flex flex-col gap-2 text-body">
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
          </section>

          <section aria-label="About">
            <SectionTitle>About</SectionTitle>
            <p className="text-body text-text-muted">
              Voice model: <span className="text-text">{settings.models.voice_model}</span>. It cannot be changed.
            </p>
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
