<template>
  <SettingsCard flush>
    <SettingsRow :label="$t('settings.injection.coreRules')" :description="$t('settings.injection.coreRulesDesc')">
      <SwitchToggle
        v-model="localConfig.core_rules"
        :width="40"
        :height="22"
        :aria-label="$t('settings.injection.coreRules')"
        @change="handleChange"
      />
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.injection.externalCodingGuidance')"
      :description="$t('settings.injection.externalCodingGuidanceDesc')"
    >
      <SwitchToggle
        v-model="localConfig.external_coding_guidance"
        :width="40"
        :height="22"
        :aria-label="$t('settings.injection.externalCodingGuidance')"
        @change="handleChange"
      />
    </SettingsRow>

    <SettingsRow :label="$t('settings.injection.skillsSummary')" :description="$t('settings.injection.skillsSummaryDesc')">
      <SwitchToggle
        v-model="localConfig.skills_summary"
        :width="40"
        :height="22"
        :aria-label="$t('settings.injection.skillsSummary')"
        @change="handleChange"
      />
    </SettingsRow>

    <SettingsRow :label="$t('settings.injection.skillsAlways')" :description="$t('settings.injection.skillsAlwaysDesc')">
      <SwitchToggle
        v-model="localConfig.skills_always"
        :width="40"
        :height="22"
        :aria-label="$t('settings.injection.skillsAlways')"
        @change="handleChange"
      />
    </SettingsRow>

    <SettingsRow :label="$t('settings.injection.agentTeams')" :description="$t('settings.injection.agentTeamsDesc')">
      <SwitchToggle
        v-model="localConfig.agent_teams"
        :width="40"
        :height="22"
        :aria-label="$t('settings.injection.agentTeams')"
        @change="handleChange"
      />
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.injection.dynamicContext')"
      :description="$t('settings.injection.dynamicContextDesc')"
    >
      <SwitchToggle
        v-model="localConfig.dynamic_context"
        :width="40"
        :height="22"
        :aria-label="$t('settings.injection.dynamicContext')"
        @change="handleChange"
      />
    </SettingsRow>

    <SettingsRow :label="$t('settings.injection.teamReminder')" :description="$t('settings.injection.teamReminderDesc')">
      <SwitchToggle
        v-model="localConfig.team_reminder"
        :width="40"
        :height="22"
        :aria-label="$t('settings.injection.teamReminder')"
        @change="handleChange"
      />
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.injection.autoMemorySummary')"
      :description="$t('settings.injection.autoMemorySummaryDesc')"
    >
      <SwitchToggle
        v-model="localConfig.auto_memory_summary"
        :width="40"
        :height="22"
        :aria-label="$t('settings.injection.autoMemorySummary')"
        @change="handleChange"
      />
    </SettingsRow>

    <SettingsRow
      :label="$t('settings.injection.disabledTools')"
      :description="$t('settings.injection.disabledToolsDesc')"
      layout="block"
    >
      <div class="tools-grid">
        <label
          v-for="tool in toolCatalog"
          :key="tool"
          class="tool-item"
          :class="{ 'is-off': isToolDisabled(tool) }"
        >
          <input type="checkbox" :checked="!isToolDisabled(tool)" @change="toggleTool(tool)">
          <span class="tool-name">{{ tool }}</span>
        </label>
      </div>
      <p class="tools-warning">
        <component :is="AlertTriangleIcon" :size="13" />
        <span>{{ $t('settings.injection.toolsWarning') }}</span>
      </p>
    </SettingsRow>
  </SettingsCard>

  <p class="page-note">
    <component :is="InfoIcon" :size="13" />
    <span>{{ $t('settings.injection.saveHint') }}</span>
  </p>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { AlertTriangle as AlertTriangleIcon, Info as InfoIcon } from 'lucide-vue-next'
import { useSettingsStore } from '@/store/settings'
import type { InjectionConfig } from '@/store/settings'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import { SettingsCard, SettingsRow } from './ui'

const settingsStore = useSettingsStore()

const defaults: InjectionConfig = {
  core_rules: true,
  external_coding_guidance: true,
  skills_always: true,
  skills_summary: true,
  agent_teams: true,
  dynamic_context: true,
  team_reminder: true,
  disabled_tools: [],
  auto_memory_summary: true,
}

// 工具名与后端 register_all_tools 的注册清单保持一致
const toolCatalog = [
  'read_file',
  'write_file',
  'edit_file',
  'exec',
  'list_dir',
  'file_search',
  'web_fetch',
  'memory',
  'wiki',
  'screenshot',
  'send_media',
  'spawn',
  'workflow_run',
  'external_coding_agent',
]

const localConfig = ref<InjectionConfig>({ ...defaults })

const syncFromStore = () => {
  const incoming = settingsStore.settings?.injection
  if (incoming) {
    localConfig.value = { ...defaults, ...incoming }
  }
}

onMounted(syncFromStore)
watch(() => settingsStore.settings?.injection, syncFromStore, { deep: true })

const isToolDisabled = (name: string) => localConfig.value.disabled_tools.includes(name)

const handleChange = () => {
  settingsStore.updateInjection({ ...localConfig.value })
}

const toggleTool = (name: string) => {
  const disabled = new Set(localConfig.value.disabled_tools)
  if (disabled.has(name)) {
    disabled.delete(name)
  } else {
    disabled.add(name)
  }
  localConfig.value.disabled_tools = toolCatalog.filter((tool) => disabled.has(tool))
  handleChange()
}
</script>

<style scoped>
.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 6px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  background: var(--co-panel);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    border-color var(--transition-fast),
    color var(--transition-fast);
}

.tool-item:hover {
  border-color: var(--color-border-secondary);
  color: var(--color-text-primary);
}

.tool-item input {
  margin: 0;
  accent-color: var(--color-primary);
}

.tool-item.is-off {
  color: var(--color-text-disabled);
  text-decoration: line-through;
}

.tool-name {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tools-warning {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 0;
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-tertiary);
}

.page-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 12px 0 0;
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-tertiary);
}
</style>
