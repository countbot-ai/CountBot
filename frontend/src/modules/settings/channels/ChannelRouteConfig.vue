<template>
  <section class="route-panel">
    <div class="route-panel-header">
      <div>
        <h5 class="route-panel-title">{{ t('settings.channels.routing.title') }}</h5>
        <p class="route-panel-desc">{{ t('settings.channels.routing.description') }}</p>
      </div>
    </div>

    <div class="route-mode-tabs" role="tablist" :aria-label="t('settings.channels.routing.title')">
      <button
        type="button"
        class="route-mode-tab"
        :class="{ active: routingMode === 'ai' }"
        @click="setRoutingMode('ai')"
      >
        <span class="route-mode-name">{{ t('settings.channels.routing.ai') }}</span>
      </button>
      <button
        type="button"
        class="route-mode-tab"
        :class="{ active: routingMode === 'direct' }"
        @click="setRoutingMode('direct')"
      >
        <span class="route-mode-name">{{ t('settings.channels.routing.direct') }}</span>
      </button>
    </div>

    <div class="route-field">
      <label class="route-label">
        {{ t('settings.channels.routing.defaultProfile') }}
      </label>
      <select
        :value="selectedProfile"
        class="route-select"
        :disabled="profileOptions.length === 0"
        @change="handleProfileChange"
      >
        <option value="">{{ t('settings.channels.routing.profilePlaceholder') }}</option>
        <option
          v-for="profile in profileOptions"
          :key="profile.name"
          :value="profile.name"
        >
          {{ profile.label }}
        </option>
      </select>
      <p v-if="profileOptions.length === 0" class="route-hint">{{ t('settings.channels.routing.noProfiles') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useExternalCodingToolsStore } from '@/store/externalCodingTools'

interface Props {
  model: Record<string, any>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  change: []
}>()

const { t } = useI18n()
const store = useExternalCodingToolsStore()

const normalizeRouteMode = (value: unknown) =>
  String(value || 'ai').trim().toLowerCase() === 'direct' ? 'direct' : 'ai'

const profileOptions = computed(() => {
  const namedProfiles = (store.config?.profiles || [])
    .filter(profile => String(profile.name || '').trim())
    .map(profile => ({
      name: profile.name.trim(),
      enabled: Boolean(profile.enabled),
      label: profile.enabled
        ? profile.name.trim()
        : `${profile.name.trim()} (${t('settings.channels.routing.profileDisabled')})`
    }))

  return namedProfiles.sort((left, right) => Number(right.enabled) - Number(left.enabled))
})

const routingMode = computed(() => normalizeRouteMode(props.model.routing_mode))
const selectedProfile = computed(() => String(props.model.external_coding_profile || '').trim())

const ensureDefaultProfile = () => {
  if (selectedProfile.value || profileOptions.value.length === 0) {
    return
  }
  const preferredProfile = profileOptions.value.find(profile => profile.enabled) || profileOptions.value[0]
  props.model.external_coding_profile = preferredProfile.name
}

const setRoutingMode = (mode: 'ai' | 'direct') => {
  props.model.routing_mode = mode
  if (mode === 'direct') {
    ensureDefaultProfile()
  }
  emit('change')
}

const handleProfileChange = (event: Event) => {
  props.model.external_coding_profile = (event.target as HTMLSelectElement).value
  emit('change')
}

onMounted(async () => {
  if (!props.model.routing_mode) {
    props.model.routing_mode = 'ai'
  }
  if (props.model.external_coding_profile === undefined || props.model.external_coding_profile === null) {
    props.model.external_coding_profile = ''
  }

  if (!store.config) {
    try {
      await store.loadConfig()
    } catch {
      return
    }
  }

  if (routingMode.value === 'direct') {
    ensureDefaultProfile()
    emit('change')
  }
})
</script>

<style scoped>
.route-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.72);
}

.route-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.route-panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.route-panel-desc,
.route-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.route-mode-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.route-mode-tab {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0 !important;
  min-height: auto !important;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.22) !important;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8) !important;
  color: inherit !important;
  box-shadow: none !important;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
  text-align: left;
}

.route-mode-tab:hover {
  border-color: rgba(59, 130, 246, 0.28) !important;
  background: rgba(59, 130, 246, 0.04) !important;
  box-shadow: none !important;
}

.route-mode-tab.active {
  border-color: rgba(59, 130, 246, 0.4) !important;
  background: rgba(59, 130, 246, 0.08) !important;
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.08) inset !important;
}

.route-mode-tab:focus,
.route-mode-tab:focus-visible {
  outline: none !important;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12) !important;
}

.route-mode-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.route-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.route-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.route-select {
  width: 100%;
  min-height: 42px;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
}

.route-select:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
}

.route-select:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

:root[data-theme='dark'] .route-panel {
  border-color: rgba(56, 70, 90, 0.58);
  background: linear-gradient(180deg, rgba(24, 31, 41, 0.98), rgba(18, 24, 33, 0.99));
}

:root[data-theme='dark'] .route-mode-tab {
  border-color: rgba(56, 70, 90, 0.58) !important;
  background: rgba(20, 27, 36, 0.92) !important;
  box-shadow: none !important;
}

:root[data-theme='dark'] .route-mode-tab:hover {
  border-color: rgba(121, 143, 182, 0.32) !important;
  background: rgba(44, 57, 76, 0.28) !important;
}

:root[data-theme='dark'] .route-mode-tab.active {
  border-color: rgba(121, 143, 182, 0.42) !important;
  background: rgba(59, 130, 246, 0.14) !important;
  box-shadow: 0 0 0 1px rgba(121, 143, 182, 0.12) inset !important;
}

:root[data-theme='dark'] .route-mode-tab:focus,
:root[data-theme='dark'] .route-mode-tab:focus-visible {
  box-shadow: 0 0 0 3px rgba(127, 181, 214, 0.16) !important;
}

@media (max-width: 640px) {
  .route-mode-tabs {
    grid-template-columns: 1fr;
  }
}
</style>
