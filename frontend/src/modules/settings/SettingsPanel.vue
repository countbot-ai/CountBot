<template>
  <div class="settings-panel">
    <!-- 侧边栏导航 -->
    <aside class="sidebar" :class="{ 'is-collapsed': sidebarCollapsed }">
      <div class="sidebar-header">
        <h2 v-if="!sidebarCollapsed">{{ $t('settings.title') }}</h2>
        <button class="collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? $t('common.expand') : $t('common.collapse')">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
            <path v-if="sidebarCollapsed" fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd"/>
            <path v-else fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
          </svg>
        </button>
      </div>
      <nav class="nav-menu">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="nav-item"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
          :title="sidebarCollapsed ? $t(tab.label) : ''"
        >
          <component
            :is="tab.icon"
            :size="20"
            class="nav-icon"
          />
          <span class="nav-label">{{ $t(tab.shortLabel || tab.label) }}</span>
          <div v-if="activeTab === tab.id" class="active-indicator"></div>
        </button>
      </nav>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 标签页内容 -->
      <div class="content-wrapper">
        <div
          :key="activeTab"
          class="tab-pane"
          :class="{ 'tab-pane-full': activeTab === 'memory' }"
        >
          <GeneralConfig v-if="activeTab === 'general'" />

          <ProviderConfig v-else-if="activeTab === 'provider'" />

          <ModelConfig v-else-if="activeTab === 'model'" />

          <div v-else-if="activeTab === 'persona'" class="persona-tabs">
            <div class="persona-tab-buttons">
              <button
                class="persona-tab-btn"
                :class="{ active: personaSubTab === 'config' }"
                @click="personaSubTab = 'config'"
              >
                {{ $t('settings.persona.basicConfig') }}
              </button>
              <button
                class="persona-tab-btn"
                :class="{ active: personaSubTab === 'editor' }"
                @click="personaSubTab = 'editor'"
              >
                {{ $t('settings.persona.personalityEditor') }}
              </button>
            </div>
            <div class="persona-tab-content">
              <PersonaConfig v-if="personaSubTab === 'config'" />
              <PersonalityEditor v-else-if="personaSubTab === 'editor'" />
            </div>
          </div>

          <MemoryPanel v-else-if="activeTab === 'memory'" />

          <WorkspaceConfig v-else-if="activeTab === 'workspace'" />

          <SecurityConfig v-else-if="activeTab === 'security'" />

          <ChannelsConfig v-else-if="activeTab === 'channels'" />

          <McpPanel v-else-if="activeTab === 'mcp'" />

          <ExternalCodingToolsConfig
            v-else-if="activeTab === 'externaltools'"
            ref="externalCodingToolsPanelRef"
          />

          <MultiAgentConfig v-else-if="activeTab === 'multiagent'" />

          <ConfigImportExport v-else-if="activeTab === 'importexport'" />
        </div>
      </div>

      <!-- 底部操作栏 -->
      <footer class="footer">
          <div class="footer-content">
            <div class="footer-left">
            <span class="save-hint">{{ footerSaveHint }}</span>
          </div>
          <div class="footer-actions">
            <button
              class="action-button action-button-close"
              @click="handleCancel"
            >
              {{ $t('common.close') }}
            </button>
            <button
              class="action-button action-button-save"
              :disabled="settingsStore.saving"
              @click="handleSave"
            >
              <span v-if="!settingsStore.saving">{{ $t('common.save') }}</span>
              <span v-else class="loading-dots">保存中</span>
            </button>
            <button
              class="action-button action-button-save-all"
              :disabled="settingsStore.saving"
              @click="handleSaveAll"
            >
              <span v-if="!settingsStore.saving">{{ $t('settings.saveAll') }}</span>
              <span v-else class="loading-dots">保存中</span>
            </button>
          </div>
        </div>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Brain as BrainIcon,
  Server as ServerIcon,
  Sliders as SlidersIcon,
  User as PersonIcon,
  FolderOpen as FolderIcon,
  Shield as ShieldIcon,
  MessageSquare as MessageIcon,
  Cpu as CpuIcon,
  TerminalSquare as TerminalSquareIcon,
  Network as NetworkIcon,
  Download as DownloadIcon,
  Settings as SettingsIcon
} from 'lucide-vue-next'
import ProviderConfig from './ProviderConfig.vue'
import ModelConfig from './ModelConfig.vue'
import PersonaConfig from './PersonaConfig.vue'
import PersonalityEditor from './PersonalityEditor.vue'
import WorkspaceConfig from './WorkspaceConfig.vue'
import SecurityConfig from './SecurityConfig.vue'
import ChannelsConfig from './ChannelsConfig.vue'
import McpPanel from '@/modules/mcp/McpPanel.vue'
import ExternalCodingToolsConfig from './ExternalCodingToolsConfig.vue'
import MultiAgentConfig from './MultiAgentConfig.vue'
import ConfigImportExport from './ConfigImportExport.vue'
import GeneralConfig from './GeneralConfig.vue'
import MemoryPanel from '@/modules/memory/MemoryPanel.vue'
import { useSettingsStore } from '@/store/settings'
import { useChannelsStore } from '@/store/channels'
import { useExternalCodingToolsStore } from '@/store/externalCodingTools'
import { useToast } from '@/composables/useToast'
import type { SettingsTab } from '@/types/settings'

interface Props {
  initialTab?: SettingsTab
}

const props = withDefaults(defineProps<Props>(), {
  initialTab: 'general'
})

const { t } = useI18n()
const settingsStore = useSettingsStore()
const channelsStore = useChannelsStore()
const externalCodingToolsStore = useExternalCodingToolsStore()
const toast = useToast()

const activeTab = ref<SettingsTab>(props.initialTab)
const personaSubTab = ref<'config' | 'editor'>('config')
const sidebarCollapsed = ref(window.innerWidth < 768) // 小屏幕默认折叠
const externalCodingToolsPanelRef = ref<{ saveConfig: () => Promise<boolean> } | null>(null)

// 监听 initialTab 变化
watch(() => props.initialTab, (newTab) => {
  if (newTab) {
    activeTab.value = newTab
  }
})

const tabs = [
  { id: 'general' as SettingsTab, icon: SettingsIcon, label: 'settings.tabs.general', shortLabel: 'settings.tabShort.general' },
  { id: 'provider' as SettingsTab, icon: ServerIcon, label: 'settings.tabs.provider', shortLabel: 'settings.tabShort.provider' },
  { id: 'model' as SettingsTab, icon: SlidersIcon, label: 'settings.tabs.model', shortLabel: 'settings.tabShort.model' },
  { id: 'persona' as SettingsTab, icon: PersonIcon, label: 'settings.tabs.persona', shortLabel: 'settings.tabShort.persona' },
  { id: 'memory' as SettingsTab, icon: BrainIcon, label: 'settings.tabs.memory', shortLabel: 'settings.tabShort.memory' },
  { id: 'workspace' as SettingsTab, icon: FolderIcon, label: 'settings.tabs.workspace', shortLabel: 'settings.tabShort.workspace' },
  { id: 'security' as SettingsTab, icon: ShieldIcon, label: 'settings.tabs.security', shortLabel: 'settings.tabShort.security' },
  { id: 'channels' as SettingsTab, icon: MessageIcon, label: 'settings.tabs.channels', shortLabel: 'settings.tabShort.channels' },
  { id: 'mcp' as SettingsTab, icon: CpuIcon, label: 'settings.tabs.mcp', shortLabel: 'settings.tabShort.mcp' },
  { id: 'externaltools' as SettingsTab, icon: TerminalSquareIcon, label: 'settings.tabs.externaltools', shortLabel: 'settings.tabShort.externaltools' },
  { id: 'multiagent' as SettingsTab, icon: NetworkIcon, label: 'settings.tabs.multiagent', shortLabel: 'settings.tabShort.multiagent' },
  { id: 'importexport' as SettingsTab, icon: DownloadIcon, label: 'settings.importExport.title', shortLabel: 'settings.importExport.title' }
]

const footerSaveHint = computed(() => {
  if (activeTab.value === 'provider' || activeTab.value === 'model') {
    return t('settings.footer.providerModel')
  }
  if (activeTab.value === 'channels') {
    return t('settings.footer.channels')
  }
  if (activeTab.value === 'mcp') {
    return t('settings.footer.noSave')
  }
  if (activeTab.value === 'externaltools') {
    return t('settings.footer.externalTools')
  }
  if (activeTab.value === 'multiagent' || activeTab.value === 'importexport') {
    return t('settings.footer.noSave')
  }
  return t('settings.saveHint')
})

const emit = defineEmits<{
  close: []
  saved: []
}>()

const handleSave = async () => {
  try {
    const currentSettings = settingsStore.settings
    if (!currentSettings) {
      toast.error(t('settings.loadError'), t('common.error'))
      return
    }

    // 根据当前标签页只保存对应的配置
    let savePayload: any = {}
    
    switch (activeTab.value) {
      case 'general':
        // 通用配置 - 暂时保存所有（如果有具体字段可以细化）
        savePayload = { ...currentSettings }
        break
        
      case 'provider':
        // 提供商与模型参数共用一组草稿
        savePayload = {
          providers: currentSettings.providers,
          model: currentSettings.model
        }
        break
        
      case 'model':
        // 提供商与模型参数共用一组草稿
        savePayload = {
          providers: currentSettings.providers,
          model: currentSettings.model
        }
        break
        
      case 'persona':
        // 只保存用户配置
        savePayload = {
          persona: currentSettings.persona
        }
        break

      case 'memory':
        toast.info(t('settings.memory.noManualSaveNeeded'), '提示')
        return
        
      case 'workspace':
        // 只保存工作区配置
        savePayload = {
          workspace: currentSettings.workspace
        }
        break
        
      case 'security':
        // 只保存安全配置
        savePayload = {
          security: currentSettings.security
        }
        break
        
      case 'channels':
        if (channelsStore.hasUnsavedChanges()) {
          const saved = await channelsStore.saveAllChannels()
          if (!saved) {
            throw new Error(channelsStore.error || 'Failed to save channel configurations')
          }
        }
        toast.success(t('settings.saveSuccess'), t('common.success'))
        emit('saved')
        return

      case 'mcp':
        toast.info(t('settings.footer.noSave'), '提示')
        return

      case 'externaltools':
        await externalCodingToolsPanelRef.value?.saveConfig()
        toast.success(t('settings.saveSuccess'), t('common.success'))
        emit('saved')
        return
        
      case 'multiagent':
        toast.info('多智能体配置已在当前页面独立保存', '提示')
        return
        break
        
      case 'importexport':
        // 配置管理页面不需要保存
        toast.info('配置管理页面无需保存', '提示')
        return
        
      default:
        // 默认保存所有
        savePayload = { ...currentSettings }
    }
    
    await settingsStore.saveSettings(savePayload)
    toast.success(t('settings.saveSuccess'), t('common.success'))
    emit('saved')
    // 不再自动关闭，保留在当前页面
    // emit('close')
  } catch (error) {
    console.error('Failed to save settings:', error)
    toast.error(t('settings.saveError'), t('common.error'))
  }
}

const handleSaveAll = async () => {
  try {
    const currentSettings = settingsStore.settings
    if (!currentSettings) {
      toast.error(t('settings.loadError'), t('common.error'))
      return
    }

    // 保存所有配置
    await settingsStore.saveSettings({ ...currentSettings }, { includeChannels: true })
    if (externalCodingToolsStore.config) {
      await externalCodingToolsStore.saveConfig()
    }
    toast.success(t('settings.saveAllSuccess'), t('common.success'))
    emit('saved')
  } catch (error) {
    console.error('Failed to save all settings:', error)
    toast.error(t('settings.saveError'), t('common.error'))
  }
}

const handleCancel = () => {
  emit('close')
}

onMounted(async () => {
  try {
    await settingsStore.loadSettings()
  } catch (error) {
    console.error('Failed to load settings:', error)
    toast.error(t('settings.loadError'))
  }
})
</script>
<style scoped>
@import './styles/SettingsPanel.css';
</style>
