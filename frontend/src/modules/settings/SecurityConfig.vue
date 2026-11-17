<template>
  <SettingsCard :title="$t('settings.security.cardProtection')">
    <SettingsRow
      :label="$t('settings.security.dangerousCommands')"
      :description="$t('settings.security.dangerousCommandsDesc')"
    >
      <SwitchToggle
        v-model="localConfig.dangerous_commands_blocked"
        :width="40"
        :height="22"
        :aria-label="$t('settings.security.dangerousCommands')"
        @change="handleChange"
      />
      <button
        v-if="localConfig.dangerous_commands_blocked"
        class="row-expand"
        :class="{ 'is-open': expandedSections.denyPatterns }"
        :aria-expanded="expandedSections.denyPatterns"
        @click="expandedSections.denyPatterns = !expandedSections.denyPatterns"
      >
        <component :is="ChevronDownIcon" :size="16" />
      </button>

      <template v-if="expandedSections.denyPatterns" #below>
        <div class="detail-block">
          <div class="detail-head">
            <span class="detail-title">{{ $t('settings.security.builtInPatterns') }}</span>
            <span class="co-row-badge">{{ builtInDangerousPatterns.length }}</span>
          </div>
          <ul class="builtin-list">
            <li v-for="(item, index) in builtInDangerousPatterns" :key="`builtin-${index}`" class="builtin-item">
              <code class="pattern-code">{{ item.pattern }}</code>
              <span class="builtin-desc">{{ item.description }}</span>
            </li>
          </ul>
        </div>

        <div class="detail-block">
          <div class="detail-head">
            <span class="detail-title">{{ $t('settings.security.customDenyPatterns') }}</span>
            <button class="co-btn co-btn--secondary btn-compact" @click="addDenyPattern">
              <component :is="PlusIcon" :size="14" />
              {{ $t('settings.security.addPattern') }}
            </button>
          </div>
          <div v-if="localConfig.custom_deny_patterns.length" class="pattern-list">
            <div v-for="(_, index) in localConfig.custom_deny_patterns" :key="`deny-${index}`" class="pattern-row">
              <input
                v-model="localConfig.custom_deny_patterns[index]"
                class="co-input pattern-input"
                type="text"
                :placeholder="$t('settings.security.patternPlaceholder')"
                @change="handleChange"
              >
              <button class="icon-btn" :title="$t('settings.security.removePattern')" @click="removeDenyPattern(index)">
                <component :is="XIcon" :size="15" />
              </button>
            </div>
          </div>
          <p v-else class="detail-empty">{{ $t('settings.security.noPatternsAdded') }}</p>
        </div>
      </template>
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.security.commandWhitelist')"
      :description="$t('settings.security.commandWhitelistDesc')"
    >
      <SwitchToggle
        v-model="localConfig.command_whitelist_enabled"
        :width="40"
        :height="22"
        :aria-label="$t('settings.security.commandWhitelist')"
        @change="handleChange"
      />
      <button
        v-if="localConfig.command_whitelist_enabled"
        class="row-expand"
        :class="{ 'is-open': expandedSections.allowPatterns }"
        :aria-expanded="expandedSections.allowPatterns"
        @click="expandedSections.allowPatterns = !expandedSections.allowPatterns"
      >
        <component :is="ChevronDownIcon" :size="16" />
      </button>

      <template v-if="expandedSections.allowPatterns" #below>
        <div class="detail-block">
          <div class="detail-head">
            <span class="detail-title">{{ $t('settings.security.customAllowPatterns') }}</span>
            <button class="co-btn co-btn--secondary btn-compact" @click="addAllowPattern">
              <component :is="PlusIcon" :size="14" />
              {{ $t('settings.security.addPattern') }}
            </button>
          </div>
          <div v-if="localConfig.custom_allow_patterns.length" class="pattern-list">
            <div v-for="(_, index) in localConfig.custom_allow_patterns" :key="`allow-${index}`" class="pattern-row">
              <input
                v-model="localConfig.custom_allow_patterns[index]"
                class="co-input pattern-input"
                type="text"
                :placeholder="$t('settings.security.patternPlaceholder')"
                @change="handleChange"
              >
              <button class="icon-btn" :title="$t('settings.security.removePattern')" @click="removeAllowPattern(index)">
                <component :is="XIcon" :size="15" />
              </button>
            </div>
          </div>
          <p v-else class="detail-empty">{{ $t('settings.security.noPatternsAdded') }}</p>
        </div>
      </template>
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.workspace.isolation')"
      :description="$t('settings.workspace.isolationDesc')"
    >
      <SwitchToggle
        v-model="localConfig.restrict_to_workspace"
        :width="40"
        :height="22"
        :aria-label="$t('settings.workspace.isolation')"
        @change="handleChange"
      />
    </SettingsRow>
  </SettingsCard>

  <SettingsCard :title="$t('settings.security.cardLimits')">
    <SettingsRow :label="$t('settings.security.commandTimeout')" :description="$t('settings.security.commandTimeoutDesc')">
      <span class="co-input-unit">
        <input
          v-model.number="localConfig.command_timeout"
          class="co-input"
          type="number"
          min="10"
          max="1800"
          @input="handleChange"
        >
        {{ $t('settings.security.seconds') }}
      </span>
    </SettingsRow>

    <SettingsRow :label="$t('settings.security.subagentTimeout')" :description="$t('settings.security.subagentTimeoutDesc')">
      <span class="co-input-unit">
        <input
          v-model.number="localConfig.subagent_timeout"
          class="co-input"
          type="number"
          min="60"
          max="3600"
          step="60"
          @input="handleChange"
        >
        {{ $t('settings.security.seconds') }}
      </span>
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.security.maxOutputLength')"
      :description="$t('settings.security.maxOutputLengthDesc')"
    >
      <span class="co-input-unit">
        <input
          v-model.number="localConfig.max_output_length"
          class="co-input"
          type="number"
          min="100"
          max="1000000"
          step="1000"
          @input="handleChange"
        >
        {{ $t('settings.security.characters') }}
      </span>
    </SettingsRow>
  </SettingsCard>

  <SettingsCard :title="$t('settings.security.cardAudit')">
    <SettingsRow :label="$t('settings.security.auditLog')" :description="$t('settings.security.auditLogDesc')">
      <SwitchToggle
        v-model="localConfig.audit_log_enabled"
        :width="40"
        :height="22"
        :aria-label="$t('settings.security.auditLog')"
        @change="handleChange"
      />
    </SettingsRow>
  </SettingsCard>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import {
  ChevronDown as ChevronDownIcon,
  Plus as PlusIcon,
  X as XIcon,
} from 'lucide-vue-next'
import { useSettingsStore } from '@/store/settings'
import type { SecurityConfig } from '@/store/settings'
import apiClient from '@/api/client'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import { SettingsCard, SettingsRow } from './ui'

const settingsStore = useSettingsStore()

const localConfig = ref<SecurityConfig>({
  dangerous_commands_blocked: true,
  custom_deny_patterns: [],
  command_whitelist_enabled: false,
  custom_allow_patterns: [],
  audit_log_enabled: true,
  command_timeout: 180,
  subagent_timeout: 1200,
  max_output_length: 10000,
  restrict_to_workspace: false,
})

const expandedSections = ref({
  denyPatterns: false,
  allowPatterns: false,
})

const builtInDangerousPatterns = ref<Array<{ pattern: string; description: string; key: string }>>([])

onMounted(async () => {
  if (settingsStore.settings?.security) {
    localConfig.value = { ...settingsStore.settings.security }
  }

  try {
    const response = await apiClient.get('/settings/security/dangerous-patterns')
    const payload = response.data
    if (Array.isArray(payload?.patterns)) {
      builtInDangerousPatterns.value = payload.patterns
    }
  } catch (error) {
    console.error('Failed to load built-in dangerous patterns:', error)
  }
})

// 监听 store 变化
watch(
  () => settingsStore.settings?.security,
  (newSecurity) => {
    if (newSecurity) {
      localConfig.value = { ...newSecurity }
    }
  },
  { deep: true },
)

const handleChange = () => {
  settingsStore.updateSecurity(localConfig.value)
}

const addDenyPattern = () => {
  localConfig.value.custom_deny_patterns.push('')
}

const removeDenyPattern = (index: number) => {
  localConfig.value.custom_deny_patterns.splice(index, 1)
  handleChange()
}

const addAllowPattern = () => {
  localConfig.value.custom_allow_patterns.push('')
}

const removeAllowPattern = (index: number) => {
  localConfig.value.custom_allow_patterns.splice(index, 1)
  handleChange()
}
</script>

<style scoped>
.row-expand {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition:
    background var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-fast);
}

.row-expand:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.row-expand.is-open {
  transform: rotate(180deg);
}

.detail-block + .detail-block {
  margin-top: 14px;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.detail-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.btn-compact {
  height: 24px;
  padding: 0 8px;
  margin-left: auto;
  font-size: var(--font-size-xs);
}

.builtin-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.builtin-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
}

.pattern-code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-secondary);
}

.builtin-desc {
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.pattern-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pattern-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pattern-input {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-error);
}

.detail-empty {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
</style>
