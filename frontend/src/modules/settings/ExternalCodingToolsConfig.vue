<template>
  <div class="external-coding-config">
    <header class="panel-header">
      <div class="panel-title-row">
        <div class="panel-title-group">
          <span class="panel-eyebrow">{{ t('settings.externalTools.overviewLabel') }}</span>
          <h3 class="panel-title">{{ t('settings.externalTools.title') }}</h3>
          <p class="panel-subtitle">{{ t('settings.externalTools.description') }}</p>
          <div class="panel-highlights">
            <span class="info-chip">
              {{ t('settings.externalTools.counts.profiles', { count: totalProfilesCount }) }}
            </span>
            <span class="info-chip info-chip-success">
              {{ t('settings.externalTools.counts.enabled', { count: enabledProfilesCount }) }}
            </span>
            <span v-if="activeProfile" class="info-chip info-chip-muted">
              {{ sessionModeLabel(activeProfile.session_mode) }}
            </span>
          </div>
          <p class="panel-note">{{ t('settings.externalTools.routeHint') }}</p>
        </div>
        <div class="panel-actions">
          <button
            type="button"
            class="ghost-button icon-button"
            :title="t('settings.externalTools.help')"
            @click="showHelp = true"
          >
            <HelpCircleIcon :size="16" />
            <span>{{ t('settings.externalTools.help') }}</span>
          </button>
          <button type="button" class="ghost-button" @click="reloadConfig">
            {{ t('common.refresh') }}
          </button>
          <button type="button" class="primary-button" @click="addProfile">
            + {{ t('settings.externalTools.addProfile') }}
          </button>
        </div>
      </div>
    </header>

    <div v-if="store.loading" class="panel-state">{{ t('common.loading') }}</div>
    <div
      v-else-if="initializationError || (store.error && !config)"
      class="panel-state panel-state-error"
    >
      {{ initializationError || store.error }}
    </div>

    <template v-else-if="config">
      <div v-if="config.profiles.length === 0" class="empty-state">
        <div class="empty-illustration">
          <span class="empty-illustration-ring"></span>
          <span class="empty-illustration-icon">
            <TerminalSquareIcon :size="28" />
          </span>
        </div>
        <h4 class="empty-state-title">{{ t('settings.externalTools.emptyTitle') }}</h4>
        <p class="empty-state-text">{{ t('settings.externalTools.empty') }}</p>
        <p class="empty-state-hint">{{ t('settings.externalTools.profileHint') }}</p>
        <button type="button" class="primary-button" @click="addProfile">
          + {{ t('settings.externalTools.addProfile') }}
        </button>
      </div>

      <template v-else-if="activeProfile">
        <section class="profile-library">
          <div class="section-heading">
            <p class="section-kicker">{{ t('settings.externalTools.sections.profiles') }}</p>
            <p class="section-note">{{ t('settings.externalTools.profileHint') }}</p>
          </div>

          <div class="profile-tabs" role="tablist" :aria-label="t('settings.externalTools.title')">
            <button
              v-for="(profile, index) in config.profiles"
              :key="`profile-tab-${index}`"
              type="button"
              class="profile-tab"
              :class="{ active: index === activeProfileIndex }"
              @click="activeProfileIndex = index"
            >
              <span class="profile-tab-status" :class="{ 'is-enabled': profile.enabled }"></span>
              <span class="profile-tab-row">
                <span class="profile-tab-icon">
                  <TerminalSquareIcon :size="18" />
                </span>
                <span class="profile-tab-main">
                  {{ profileLabel(profile, index) }}
                </span>
              </span>
              <span class="profile-tab-meta">
                <span>
                  {{
                    profile.enabled
                      ? t('settings.externalTools.statusEnabled')
                      : t('settings.externalTools.statusDisabled')
                  }}
                </span>
                <span>{{ sessionModeLabel(profile.session_mode) }}</span>
                <span>{{ profileTypeLabel(profile) }}</span>
              </span>
            </button>
          </div>
        </section>

        <section class="editor-card">
          <div class="form-stack">
            <div class="editor-toolbar">
              <label class="switch-row switch-row-prominent">
                <span class="switch-copy">
                  <strong>{{ t('common.enable') }}</strong>
                  <small>{{ t('settings.externalTools.enableHint') }}</small>
                </span>
                <SwitchToggle
                  v-model="activeProfile.enabled"
                  :width="42"
                  :height="24"
                  :aria-label="t('common.enable')"
                />
              </label>
            </div>

            <section class="form-section">
              <div class="field-grid compact-grid">
                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.name') }}</label>
                  <input
                    v-model="activeProfile.name"
                    type="text"
                    class="config-input"
                    :placeholder="t('settings.externalTools.placeholders.name')"
                  >
                </div>

                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.description') }}</label>
                  <input
                    v-model="activeProfile.description"
                    type="text"
                    class="config-input"
                    :placeholder="t('settings.externalTools.placeholders.description')"
                  >
                </div>
              </div>

              <div class="field-grid compact-grid">
                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.type') }}</label>
                  <input v-model="activeProfile.type" type="text" class="config-input is-code">
                </div>

                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.timeout') }}</label>
                  <input
                    :value="activeProfile.timeout ?? ''"
                    type="number"
                    class="config-input"
                    @input="activeProfile.timeout = normalizeOptionalNumber(($event.target as HTMLInputElement).value)"
                  >
                </div>
              </div>
            </section>

            <section class="form-section">
              <div class="field-grid compact-grid">
                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.sessionMode') }}</label>
                  <select v-model="activeProfile.session_mode" class="config-input">
                    <option v-for="option in sessionModeOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </div>

                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.historyMessageCount') }}</label>
                  <input
                    v-model.number="activeProfile.history_message_count"
                    type="number"
                    min="1"
                    max="50"
                    class="config-input"
                    :disabled="activeProfile.session_mode === 'stateless'"
                  >
                </div>
              </div>

              <p class="field-hint">
                {{
                  activeProfile.session_mode === 'native'
                    ? t('settings.externalTools.nativeModeHint')
                    : t('settings.externalTools.historyModeHint')
                }}
              </p>
            </section>

            <section class="form-section">
              <div class="form-field">
                <label>{{ t('settings.externalTools.fields.command') }}</label>
                <input
                  v-model="activeProfile.command"
                  type="text"
                  class="config-input is-code"
                  :placeholder="t('settings.externalTools.placeholders.command')"
                >
                <p class="field-hint">{{ t('settings.externalTools.commandHint') }}</p>
              </div>

              <div class="form-field">
                <label>{{ t('settings.externalTools.fields.args') }}</label>
                <textarea
                  :value="joinLines(activeProfile.args)"
                  class="config-textarea is-code"
                  rows="4"
                  :placeholder="ARGS_PLACEHOLDER"
                  @input="updateLines(activeProfile, 'args', ($event.target as HTMLTextAreaElement).value)"
                ></textarea>
                <p class="field-hint">{{ t('settings.externalTools.argsHint') }}</p>
              </div>

              <div class="form-field">
                <label>{{ t('settings.externalTools.fields.workingDir') }}</label>
                <input
                  v-model="activeProfile.working_dir"
                  type="text"
                  class="config-input is-code"
                  :placeholder="t('settings.externalTools.placeholders.workingDir')"
                >
                <p class="field-hint">{{ t('settings.externalTools.workingDirHint') }}</p>
              </div>
            </section>

            <section class="form-section">
              <div class="field-grid compact-grid">
                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.aliases') }}</label>
                  <textarea
                    :value="joinLines(activeProfile.aliases)"
                    class="config-textarea is-code"
                    rows="3"
                    :placeholder="t('settings.externalTools.placeholders.aliases')"
                    @input="updateLines(activeProfile, 'aliases', ($event.target as HTMLTextAreaElement).value)"
                  ></textarea>
                </div>

                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.inheritEnv') }}</label>
                  <textarea
                    :value="joinLines(activeProfile.inherit_env)"
                    class="config-textarea is-code"
                    rows="3"
                    :placeholder="t('settings.externalTools.placeholders.inheritEnv')"
                    @input="updateLines(activeProfile, 'inherit_env', ($event.target as HTMLTextAreaElement).value)"
                  ></textarea>
                </div>
              </div>

              <div class="form-field">
                <label>{{ t('settings.externalTools.fields.env') }}</label>
                <textarea
                  :value="getEnvDraft(activeProfileIndex)"
                  class="config-textarea is-code"
                  rows="6"
                  :placeholder="ENV_PLACEHOLDER"
                  @input="updateEnv(activeProfile, activeProfileIndex, ($event.target as HTMLTextAreaElement).value)"
                ></textarea>
                <p class="field-hint">{{ t('settings.externalTools.envHint') }}</p>
              </div>
            </section>

            <details class="advanced-panel">
              <summary>{{ t('settings.externalTools.advanced') }}</summary>

              <div class="advanced-content">
                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.successExitCodes') }}</label>
                  <input
                    :value="joinNumbers(activeProfile.success_exit_codes)"
                    type="text"
                    class="config-input is-code"
                    @input="updateNumberList(activeProfile, ($event.target as HTMLInputElement).value)"
                  >
                </div>

                <div class="form-field">
                  <label>{{ t('settings.externalTools.fields.stdinTemplate') }}</label>
                  <textarea
                    :value="activeProfile.stdin_template || ''"
                    class="config-textarea is-code"
                    rows="4"
                    @input="activeProfile.stdin_template = normalizeOptionalText(($event.target as HTMLTextAreaElement).value)"
                  ></textarea>
                </div>
              </div>
            </details>

            <details class="advanced-panel utility-panel">
              <summary>{{ t('settings.externalTools.moreActions') }}</summary>

              <div class="advanced-content utility-actions">
                <label class="switch-row">
                  <span>{{ t('common.enable') }}</span>
                  <SwitchToggle
                    v-model="activeProfile.enabled"
                    :width="42"
                    :height="24"
                    :aria-label="t('common.enable')"
                  />
                </label>

                <button
                  type="button"
                  class="ghost-button"
                  :disabled="isCheckingActive"
                  @click="runCheck(activeProfile)"
                >
                  {{ isCheckingActive ? t('common.testing') : t('settings.externalTools.checkProfile') }}
                </button>

                <button type="button" class="danger-button" @click="removeProfile(activeProfileIndex)">
                  {{ t('common.delete') }}
                </button>
              </div>
            </details>
          </div>

          <div v-if="profileErrors[activeProfileIndex]" class="inline-message inline-message-error">
            {{ profileErrors[activeProfileIndex] }}
          </div>

        </section>
      </template>
    </template>
  </div>

  <Modal
    v-model="showHelp"
    :title="t('settings.externalTools.helpTitle')"
    size="medium"
    :show-footer="false"
  >
    <div class="help-content">
      <section class="help-section">
        <h4>{{ t('settings.externalTools.helpQuickStartTitle') }}</h4>
        <ol class="help-list">
          <li>{{ t('settings.externalTools.helpQuickStartStep1') }}</li>
          <li>{{ t('settings.externalTools.helpQuickStartStep2') }}</li>
          <li>{{ t('settings.externalTools.helpQuickStartStep3') }}</li>
          <li>{{ t('settings.externalTools.helpQuickStartStep4') }}</li>
        </ol>
      </section>

      <section class="help-section">
        <h4>{{ t('settings.externalTools.helpImTitle') }}</h4>
        <ol class="help-list">
          <li>{{ t('settings.externalTools.helpImStep1') }}</li>
          <li>{{ t('settings.externalTools.helpImStep2') }}</li>
          <li>{{ t('settings.externalTools.helpImStep3') }}</li>
          <li>{{ t('settings.externalTools.helpImStep4') }}</li>
        </ol>
      </section>

      <section class="help-section">
        <h4>{{ t('settings.externalTools.helpCommandsTitle') }}</h4>
        <p>{{ t('settings.externalTools.helpCommandsBody') }}</p>
        <pre class="help-code">用 claude 帮我写一个 python 爬虫
用 codex 修复这个报错
用 opencode 重构这个模块</pre>
      </section>

      <section class="help-section">
        <h4>{{ t('settings.externalTools.helpModesTitle') }}</h4>
        <ol class="help-list">
          <li>{{ t('settings.externalTools.helpModesStep1') }}</li>
          <li>{{ t('settings.externalTools.helpModesStep2') }}</li>
          <li>{{ t('settings.externalTools.helpModesStep3') }}</li>
        </ol>
      </section>

      <section class="help-section">
        <h4>{{ t('settings.externalTools.helpRoutingTitle') }}</h4>
        <p>{{ t('settings.externalTools.helpRoutingBody') }}</p>
        <pre class="help-code">/coder codex
/cdr claude
/route direct
/rt ai
/coder default
/route default</pre>
      </section>

      <section class="help-section">
        <h4>{{ t('settings.externalTools.helpFieldsTitle') }}</h4>
        <ol class="help-list">
          <li>{{ t('settings.externalTools.helpFieldsStep1') }}</li>
          <li>{{ t('settings.externalTools.helpFieldsStep2') }}</li>
          <li>{{ t('settings.externalTools.helpFieldsStep3') }}</li>
          <li>{{ t('settings.externalTools.helpFieldsStep4') }}</li>
        </ol>
      </section>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { HelpCircle as HelpCircleIcon, TerminalSquare as TerminalSquareIcon } from 'lucide-vue-next'
import { useExternalCodingToolsStore } from '@/store/externalCodingTools'
import { useToast } from '@/composables/useToast'
import Modal from '@/components/ui/Modal.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import type { ExternalCodingToolProfile } from '@/api'

const { t } = useI18n()
const store = useExternalCodingToolsStore()
const toast = useToast()

const activeProfileIndex = ref(0)
const showHelp = ref(false)
const profileErrors = ref<Record<number, string>>({})
const envDrafts = ref<Record<number, string>>({})
const initializationError = ref<string | null>(null)

const config = computed(() => store.config)
const sessionModeOptions = computed(() => [
  { value: 'stateless', label: t('settings.externalTools.sessionModes.stateless') },
  { value: 'history', label: t('settings.externalTools.sessionModes.history') },
  { value: 'native', label: t('settings.externalTools.sessionModes.native') }
])
const activeProfile = computed(() => config.value?.profiles[activeProfileIndex.value] ?? null)
const totalProfilesCount = computed(() => config.value?.profiles.length || 0)
const enabledProfilesCount = computed(
  () => (config.value?.profiles || []).filter(profile => profile.enabled).length
)
const isCheckingActive = computed(() => {
  const profile = activeProfile.value
  if (!profile) {
    return false
  }
  return store.checking === (profile.name || 'profile')
})

const joinLines = (items: string[]) => (items || []).join('\n')
const joinNumbers = (items: number[]) => (items || []).join(', ')
const normalizeOptionalText = (value: string) => value.trim() || null
const ARGS_PLACEHOLDER = '--print\n{prompt}'
const ENV_PLACEHOLDER = '{\n  "ANTHROPIC_API_KEY": "..."\n}'
const isFiniteNumber = (value: number) => typeof value === 'number' && isFinite(value)
const isIntegerNumber = (value: number) => isFiniteNumber(value) && Math.floor(value) === value
const normalizeSessionMode = (value: string) => {
  const mode = String(value || '').trim().toLowerCase()
  if (mode === 'stateless' || mode === 'history' || mode === 'native') {
    return mode
  }
  return 'history'
}
const normalizeOptionalNumber = (value: string) => {
  const text = value.trim()
  if (!text) {
    return null
  }
  const parsed = Number(text)
  return isFiniteNumber(parsed) ? parsed : null
}
const stringifyJson = (value: Record<string, string>) => JSON.stringify(value || {}, null, 2)
const sessionModeLabel = (mode: ExternalCodingToolProfile['session_mode']) =>
  t(`settings.externalTools.sessionModes.${normalizeSessionMode(mode)}`)

const profileTypeLabel = (profile: ExternalCodingToolProfile | null) =>
  String(profile?.type || 'cli').trim().toUpperCase()

const profileLabel = (profile: ExternalCodingToolProfile | null, index: number) => {
  const name = String(profile?.name || '').trim()
  if (name) {
    return name
  }
  return `${t('settings.externalTools.profile')} ${index + 1}`
}

const resetDraftState = () => {
  const nextDrafts: Record<number, string> = {}
  const profiles = config.value?.profiles || []
  for (let index = 0; index < profiles.length; index += 1) {
    nextDrafts[index] = stringifyJson(profiles[index].env)
  }
  envDrafts.value = nextDrafts
  profileErrors.value = {}
}

const getEnvDraft = (index: number) => {
  if (!(index in envDrafts.value) && config.value?.profiles[index]) {
    envDrafts.value[index] = stringifyJson(config.value.profiles[index].env)
  }
  return envDrafts.value[index] || '{}'
}

const clampActiveIndex = () => {
  const total = config.value?.profiles.length || 0
  if (total === 0) {
    activeProfileIndex.value = 0
    return
  }
  if (activeProfileIndex.value >= total) {
    activeProfileIndex.value = total - 1
  }
}

const normalizeProfiles = () => {
  for (const profile of config.value?.profiles || []) {
    profile.session_mode = normalizeSessionMode(profile.session_mode)
    profile.history_message_count = Math.min(
      50,
      Math.max(1, Number(profile.history_message_count) || 10)
    )
  }
}

const updateLines = (
  profile: ExternalCodingToolProfile,
  field: 'args' | 'aliases' | 'inherit_env',
  value: string
) => {
  profile[field] = value
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
}

const updateNumberList = (profile: ExternalCodingToolProfile, value: string) => {
  profile.success_exit_codes = value
    .split(',')
    .map(item => Number(item.trim()))
    .filter(item => isIntegerNumber(item))
}

const updateEnv = (profile: ExternalCodingToolProfile, index: number, value: string) => {
  envDrafts.value[index] = value

  try {
    const parsed = JSON.parse(value || '{}')
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new Error('invalid object')
    }

    const nextEnv: Record<string, string> = {}
    for (const key in parsed) {
      if (Object.prototype.hasOwnProperty.call(parsed, key)) {
        nextEnv[String(key)] = String((parsed as Record<string, unknown>)[key] ?? '')
      }
    }
    profile.env = nextEnv
    delete profileErrors.value[index]
  } catch {
    profileErrors.value[index] = t('settings.externalTools.invalidJson')
  }
}

const runCheck = async (profile: ExternalCodingToolProfile) => {
  try {
    const result = await store.checkProfile(profile)
    if (result.success) {
      toast.success(result.message, t('common.success'))
    } else {
      toast.error(result.message, t('common.error'))
    }
  } catch (error: any) {
    toast.error(error.message || t('settings.externalTools.checkFailed'), t('common.error'))
  }
}

const reloadConfig = async () => {
  await initializeConfig(true)
}

const addProfile = () => {
  store.addProfile()
  normalizeProfiles()
  activeProfileIndex.value = (config.value?.profiles.length || 1) - 1
  resetDraftState()
}

const removeProfile = (index: number) => {
  store.removeProfile(index)
  clampActiveIndex()
  resetDraftState()
}

async function saveConfig() {
  normalizeProfiles()
  await store.saveConfig()
  clampActiveIndex()
  resetDraftState()
  return true
}

defineExpose({ saveConfig })

const initializeConfig = async (force = false) => {
  initializationError.value = null
  try {
    if (!store.config || force) {
      await store.loadConfig(force)
    }
    normalizeProfiles()
    clampActiveIndex()
    resetDraftState()
  } catch (error: any) {
    initializationError.value = error?.message || store.error || t('settings.loadError')
    console.error('Failed to initialize external coding tools config:', error)
  }
}

watch(
  () => config.value?.profiles.length || 0,
  () => {
    clampActiveIndex()
  }
)

onMounted(async () => {
  await initializeConfig()
})
</script>
<style scoped>
@import './styles/ExternalCodingToolsConfig.css';
</style>
