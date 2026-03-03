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
        <!-- Provider Configuration -->
        <transition name="fade" mode="out-in">
          <div
            v-if="activeTab === 'provider'"
            key="provider"
            class="tab-pane"
          >
            <ProviderConfig />
          </div>

          <!-- Model Parameters -->
          <div
            v-else-if="activeTab === 'model'"
            key="model"
            class="tab-pane"
          >
            <ModelConfig />
          </div>

          <!-- Persona Configuration -->
          <div
            v-else-if="activeTab === 'persona'"
            key="persona"
            class="tab-pane"
          >
            <div class="persona-tabs">
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
          </div>

          <!-- Workspace Configuration -->
          <div
            v-else-if="activeTab === 'workspace'"
            key="workspace"
            class="tab-pane"
          >
            <WorkspaceConfig />
          </div>

          <!-- Security Settings -->
          <div
            v-else-if="activeTab === 'security'"
            key="security"
            class="tab-pane"
          >
            <SecurityConfig />
          </div>

          <!-- Channels Configuration -->
          <div
            v-else-if="activeTab === 'channels'"
            key="channels"
            class="tab-pane"
          >
            <ChannelsConfig />
          </div>
        </transition>
      </div>

      <!-- 底部操作栏 -->
      <footer class="footer">
        <Button
          variant="secondary"
          @click="handleCancel"
        >
          {{ $t('common.cancel') }}
        </Button>
        <Button
          variant="primary"
          :loading="settingsStore.loading"
          @click="handleSave"
        >
          {{ $t('common.save') }}
        </Button>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Server as ServerIcon,
  Sliders as SlidersIcon,
  User as UserIcon,
  FolderOpen as FolderIcon,
  Shield as ShieldIcon,
  MessageSquare as MessageIcon
} from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import ProviderConfig from './ProviderConfig.vue'
import ModelConfig from './ModelConfig.vue'
import PersonaConfig from './PersonaConfig.vue'
import PersonalityEditor from './PersonalityEditor.vue'
import WorkspaceConfig from './WorkspaceConfig.vue'
import SecurityConfig from './SecurityConfig.vue'
import ChannelsConfig from './ChannelsConfig.vue'
import { useSettingsStore } from '@/store/settings'
import { useToast } from '@/composables/useToast'
import type { SettingsTab } from '@/types/settings'

const { t } = useI18n()
const settingsStore = useSettingsStore()
const toast = useToast()

const activeTab = ref<SettingsTab>('provider')
const personaSubTab = ref<'config' | 'editor'>('config')
const sidebarCollapsed = ref(window.innerWidth < 768) // 小屏幕默认折叠

const tabs = [
  { id: 'provider' as SettingsTab, icon: ServerIcon, label: 'settings.tabs.provider', shortLabel: 'settings.tabShort.provider' },
  { id: 'model' as SettingsTab, icon: SlidersIcon, label: 'settings.tabs.model', shortLabel: 'settings.tabShort.model' },
  { id: 'persona' as SettingsTab, icon: UserIcon, label: 'settings.tabs.persona', shortLabel: 'settings.tabShort.persona' },
  { id: 'workspace' as SettingsTab, icon: FolderIcon, label: 'settings.tabs.workspace', shortLabel: 'settings.tabShort.workspace' },
  { id: 'security' as SettingsTab, icon: ShieldIcon, label: 'settings.tabs.security', shortLabel: 'settings.tabShort.security' },
  { id: 'channels' as SettingsTab, icon: MessageIcon, label: 'settings.tabs.channels', shortLabel: 'settings.tabShort.channels' }
]

const emit = defineEmits<{
  close: []
  saved: []
}>()

const handleSave = async () => {
  try {
    await settingsStore.saveSettings(settingsStore.settings)
    toast.success(t('settings.saveSuccess'))
    emit('saved')
    emit('close')
  } catch (error) {
    console.error('Failed to save settings:', error)
    toast.error(t('settings.saveError'))
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
.settings-panel {
  display: flex;
  height: 100%;
  background: var(--bg-secondary);
}

/* 侧边栏 */
.sidebar {
  width: 120px;
  background: var(--bg-primary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.3s ease;
}

.sidebar.is-collapsed {
  width: 56px;
}

.sidebar-header {
  padding: 16px 12px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sidebar.is-collapsed .sidebar-header {
  padding: 16px 8px;
  justify-content: center;
}

.sidebar-header h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
}

.collapse-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-menu {
  flex: 1;
  padding: 12px 8px;
  overflow-y: auto;
}

.sidebar.is-collapsed .nav-menu {
  padding: 12px 4px;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 10px;
  margin-bottom: 4px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: left;
}

.sidebar.is-collapsed .nav-item {
  padding: 9px;
  justify-content: center;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.1) 100%);
  color: var(--primary-color);
}

.nav-icon {
  flex-shrink: 0;
}

.nav-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar.is-collapsed .nav-label {
  display: none;
}

.active-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  background: var(--primary-color);
  border-radius: 0 2px 2px 0;
}

/* 主内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 32px;
}

.tab-pane {
  max-width: 900px;
  margin: 0 auto;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: all 0.2s ease;
}

.fade-enter-from {
  opacity: 0;
  transform: translateX(10px);
}

.fade-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}

/* 底部操作栏 */
.footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 32px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-primary);
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
}

/* 响应式 */
@media (max-width: 768px) {
  .settings-panel {
    flex-direction: column;
  }

  .sidebar {
    width: 100% !important;
    border-right: none;
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .sidebar-header {
    display: none;
  }

  .nav-menu {
    display: flex;
    overflow-x: auto;
    padding: 6px 8px;
    gap: 2px;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }

  .nav-menu::-webkit-scrollbar {
    display: none;
  }

  .nav-item {
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    width: auto;
    padding: 8px 10px;
    text-align: center;
    flex-shrink: 0;
    border-radius: 6px;
    margin-bottom: 0;
  }

  .nav-label {
    display: block !important;
    font-size: 11px;
    white-space: nowrap;
    flex: none;
  }

  .nav-icon {
    width: 18px !important;
    height: 18px !important;
  }

  .active-indicator {
    left: 50%;
    top: auto;
    bottom: 0;
    transform: translateX(-50%);
    width: 20px;
    height: 3px;
    border-radius: 2px 2px 0 0;
  }

  .content-wrapper {
    padding: 16px;
  }

  .footer {
    padding: 12px 16px;
  }
}

@media (max-width: 480px) {
  .nav-item {
    padding: 6px 8px;
  }

  .nav-label {
    font-size: 10px;
  }

  .content-wrapper {
    padding: 12px;
  }

  .footer {
    padding: 10px 12px;
  }
}

/* Persona Sub-tabs */
.persona-tabs {
  width: 100%;
}

.persona-tab-buttons {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  border-bottom: 2px solid var(--border-color);
}

.persona-tab-btn {
  padding: 12px 20px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  position: relative;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}

.persona-tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.persona-tab-btn.active {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
}

.persona-tab-content {
  width: 100%;
}
</style>
