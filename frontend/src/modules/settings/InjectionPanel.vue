<template>
  <div class="injection-config">
    <div class="section-header">
      <h3 class="section-title">{{ $t('settings.injection.title') }}</h3>
      <p class="section-desc">{{ $t('settings.injection.description') }}</p>
    </div>

    <div class="injection-options">
      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <ScrollTextIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.coreRules') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.coreRulesDesc') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="localConfig.core_rules"
            :width="44"
            :height="24"
            :aria-label="$t('settings.injection.coreRules')"
            @change="handleChange"
          />
        </div>
      </div>

      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <TerminalIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.externalCodingGuidance') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.externalCodingGuidanceDesc') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="localConfig.external_coding_guidance"
            :width="44"
            :height="24"
            :aria-label="$t('settings.injection.externalCodingGuidance')"
            @change="handleChange"
          />
        </div>
      </div>

      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <ListChecksIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.skillsSummary') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.skillsSummaryDesc') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="localConfig.skills_summary"
            :width="44"
            :height="24"
            :aria-label="$t('settings.injection.skillsSummary')"
            @change="handleChange"
          />
        </div>
      </div>

      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <ZapIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.skillsAlways') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.skillsAlwaysDesc') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="localConfig.skills_always"
            :width="44"
            :height="24"
            :aria-label="$t('settings.injection.skillsAlways')"
            @change="handleChange"
          />
        </div>
      </div>

      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <UsersIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.agentTeams') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.agentTeamsDesc') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="localConfig.agent_teams"
            :width="44"
            :height="24"
            :aria-label="$t('settings.injection.agentTeams')"
            @change="handleChange"
          />
        </div>
      </div>

      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <ClockIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.dynamicContext') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.dynamicContextDesc') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="localConfig.dynamic_context"
            :width="44"
            :height="24"
            :aria-label="$t('settings.injection.dynamicContext')"
            @change="handleChange"
          />
        </div>
      </div>

      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <AtSignIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.teamReminder') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.teamReminderDesc') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="localConfig.team_reminder"
            :width="44"
            :height="24"
            :aria-label="$t('settings.injection.teamReminder')"
            @change="handleChange"
          />
        </div>
      </div>

      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <BrainIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.autoMemorySummary') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.autoMemorySummaryDesc') }}</p>
            </div>
          </div>
          <SwitchToggle
            v-model="localConfig.auto_memory_summary"
            :width="44"
            :height="24"
            :aria-label="$t('settings.injection.autoMemorySummary')"
            @change="handleChange"
          />
        </div>
      </div>

      <div class="injection-card">
        <div class="card-header">
          <div class="header-left">
            <WrenchIcon :size="20" class="icon" />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.injection.disabledTools') }}</h4>
              <p class="card-desc">{{ $t('settings.injection.disabledToolsDesc') }}</p>
            </div>
          </div>
        </div>
        <div class="tools-body">
          <div class="tools-grid">
            <label
              v-for="tool in toolCatalog"
              :key="tool"
              class="tool-item"
              :class="{ 'is-off': isToolDisabled(tool) }"
            >
              <input
                type="checkbox"
                :checked="!isToolDisabled(tool)"
                @change="toggleTool(tool)"
              >
              <span class="tool-name">{{ tool }}</span>
            </label>
          </div>
          <p class="tools-warning">
            <AlertTriangleIcon :size="14" />
            <span>{{ $t('settings.injection.toolsWarning') }}</span>
          </p>
        </div>
      </div>
    </div>

    <div class="save-hint">
      <InfoIcon :size="14" />
      <span>{{ $t('settings.injection.saveHint') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import {
  ScrollText as ScrollTextIcon,
  Terminal as TerminalIcon,
  ListChecks as ListChecksIcon,
  Zap as ZapIcon,
  Users as UsersIcon,
  Clock as ClockIcon,
  AtSign as AtSignIcon,
  Brain as BrainIcon,
  Wrench as WrenchIcon,
  AlertTriangle as AlertTriangleIcon,
  Info as InfoIcon
} from 'lucide-vue-next'
import { useSettingsStore } from '@/store/settings'
import type { InjectionConfig } from '@/store/settings'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'

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
  auto_memory_summary: true
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
  'external_coding_agent'
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
@import './styles/InjectionConfig.css';
</style>
