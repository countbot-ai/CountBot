<template>
  <div class="security-config">
    <div class="section-header">
      <h3 class="section-title">
        {{ $t('settings.security.title') }}
      </h3>
      <p class="section-desc">
        {{ $t('settings.security.description') }}
      </p>
    </div>

    <!-- Security Options -->
    <div class="security-options">
      <!-- API Key Encryption -->
      <div class="security-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="LockIcon"
              :size="20"
              class="icon"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.security.encryption') }}</h4>
              <p class="card-desc">{{ $t('settings.security.encryptionDesc') }}</p>
            </div>
          </div>
          <label class="toggle-switch">
            <input
              v-model="localConfig.api_key_encryption_enabled"
              type="checkbox"
              @change="handleChange"
            >
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>

      <!-- Dangerous Commands Detection -->
      <div class="security-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="AlertTriangleIcon"
              :size="20"
              class="icon icon-warning"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.security.dangerousCommands') }}</h4>
              <p class="card-desc">{{ $t('settings.security.dangerousCommandsDesc') }}</p>
            </div>
          </div>
          <div class="header-right">
            <label class="toggle-switch">
              <input
                v-model="localConfig.dangerous_commands_blocked"
                type="checkbox"
                @change="handleChange"
              >
              <span class="toggle-slider"></span>
            </label>
            <button
              v-if="localConfig.dangerous_commands_blocked"
              class="expand-btn"
              @click="expandedSections.denyPatterns = !expandedSections.denyPatterns"
            >
              <component
                :is="expandedSections.denyPatterns ? ChevronUpIcon : ChevronDownIcon"
                :size="18"
              />
            </button>
          </div>
        </div>
        
        <!-- Custom Deny Patterns -->
        <transition name="expand">
          <div
            v-if="localConfig.dangerous_commands_blocked && expandedSections.denyPatterns"
            class="card-body"
          >
            <div class="patterns-section">
              <!-- 内置危险模式 -->
              <div class="built-in-patterns">
                <div class="patterns-header">
                  <span class="patterns-title">{{ $t('settings.security.builtInPatterns') }}</span>
                  <span class="badge">{{ builtInDangerousPatterns.length }}</span>
                </div>
                <div class="patterns-grid">
                  <div
                    v-for="(item, index) in builtInDangerousPatterns"
                    :key="`builtin-${index}`"
                    class="pattern-card builtin"
                  >
                    <div class="pattern-card-header">
                      <div class="pattern-icon danger">
                        <component :is="AlertTriangleIcon" :size="16" />
                      </div>
                      <div class="pattern-info">
                        <div class="pattern-title">{{ item.description }}</div>
                        <code class="pattern-code">{{ item.pattern }}</code>
                      </div>
                      <span class="readonly-badge">{{ $t('settings.security.builtIn') }}</span>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- 自定义拒绝模式 -->
              <div class="custom-patterns">
                <div class="patterns-header">
                  <span class="patterns-title">{{ $t('settings.security.customDenyPatterns') }}</span>
                  <button
                    class="add-btn"
                    @click="addDenyPattern"
                  >
                    <component
                      :is="PlusIcon"
                      :size="16"
                    />
                    {{ $t('settings.security.addPattern') }}
                  </button>
                </div>
                <div class="patterns-list">
                  <div
                    v-for="(pattern, index) in localConfig.custom_deny_patterns"
                    :key="`deny-${index}`"
                    class="pattern-item"
                  >
                    <input
                      v-model="localConfig.custom_deny_patterns[index]"
                      type="text"
                      class="pattern-input"
                      :placeholder="$t('settings.security.patternPlaceholder')"
                      @input="handleChange"
                    >
                    <button
                      class="remove-btn"
                      @click="removeDenyPattern(index)"
                      :title="$t('settings.security.removePattern')"
                    >
                      <component
                        :is="XIcon"
                        :size="16"
                      />
                    </button>
                  </div>
                  <div
                    v-if="localConfig.custom_deny_patterns.length === 0"
                    class="empty-state"
                  >
                    <component
                      :is="InfoIcon"
                      :size="16"
                    />
                    <span>{{ $t('settings.security.noPatternsAdded') }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </transition>
      </div>

      <!-- Command Whitelist -->
      <div class="security-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="ListChecksIcon"
              :size="20"
              class="icon icon-success"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.security.commandWhitelist') }}</h4>
              <p class="card-desc">{{ $t('settings.security.commandWhitelistDesc') }}</p>
            </div>
          </div>
          <div class="header-right">
            <label class="toggle-switch">
              <input
                v-model="localConfig.command_whitelist_enabled"
                type="checkbox"
                @change="handleChange"
              >
              <span class="toggle-slider"></span>
            </label>
            <button
              v-if="localConfig.command_whitelist_enabled"
              class="expand-btn"
              @click="expandedSections.allowPatterns = !expandedSections.allowPatterns"
            >
              <component
                :is="expandedSections.allowPatterns ? ChevronUpIcon : ChevronDownIcon"
                :size="18"
              />
            </button>
          </div>
        </div>
        
        <!-- Custom Allow Patterns -->
        <transition name="expand">
          <div
            v-if="localConfig.command_whitelist_enabled && expandedSections.allowPatterns"
            class="card-body"
          >
            <div class="patterns-section">
              <div class="patterns-header">
                <span class="patterns-title">{{ $t('settings.security.customAllowPatterns') }}</span>
                <button
                  class="add-btn"
                  @click="addAllowPattern"
                >
                  <component
                    :is="PlusIcon"
                    :size="16"
                  />
                  {{ $t('settings.security.addPattern') }}
                </button>
              </div>
              <div class="patterns-list">
                <div
                  v-for="(pattern, index) in localConfig.custom_allow_patterns"
                  :key="`allow-${index}`"
                  class="pattern-item"
                >
                  <input
                    v-model="localConfig.custom_allow_patterns[index]"
                    type="text"
                    class="pattern-input"
                    :placeholder="$t('settings.security.patternPlaceholder')"
                    @input="handleChange"
                  >
                  <button
                    class="remove-btn"
                    @click="removeAllowPattern(index)"
                    :title="$t('settings.security.removePattern')"
                  >
                    <component
                      :is="XIcon"
                      :size="16"
                    />
                  </button>
                </div>
                <div
                  v-if="localConfig.custom_allow_patterns.length === 0"
                  class="empty-state"
                >
                  <component
                    :is="InfoIcon"
                    :size="16"
                  />
                  <span>{{ $t('settings.security.noPatternsAdded') }}</span>
                </div>
              </div>
            </div>
          </div>
        </transition>
      </div>

      <!-- Audit Log -->
      <div class="security-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="FileTextIcon"
              :size="20"
              class="icon icon-info"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.security.auditLog') }}</h4>
              <p class="card-desc">{{ $t('settings.security.auditLogDesc') }}</p>
            </div>
          </div>
          <label class="toggle-switch">
            <input
              v-model="localConfig.audit_log_enabled"
              type="checkbox"
              @change="handleChange"
            >
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>

      <!-- Workspace Isolation -->
      <div class="security-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="FolderLockIcon"
              :size="20"
              class="icon icon-primary"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.workspace.isolation') }}</h4>
              <p class="card-desc">{{ $t('settings.workspace.isolationDesc') }}</p>
            </div>
          </div>
          <label class="toggle-switch">
            <input
              v-model="localConfig.restrict_to_workspace"
              type="checkbox"
              @change="handleChange"
            >
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>

      <!-- Command Timeout -->
      <div class="security-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="ClockIcon"
              :size="20"
              class="icon icon-warning"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.security.commandTimeout') }}</h4>
              <p class="card-desc">{{ $t('settings.security.commandTimeoutDesc') }}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="input-group">
            <input
              v-model.number="localConfig.command_timeout"
              type="number"
              min="1"
              max="300"
              class="number-input"
              @input="handleChange"
            />
            <span class="input-suffix">{{ $t('settings.security.seconds') }}</span>
          </div>
          <p class="input-hint">{{ $t('settings.security.commandTimeoutHint') }}</p>
        </div>
      </div>

      <!-- Max Output Length -->
      <div class="security-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="MaximizeIcon"
              :size="20"
              class="icon icon-info"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.security.maxOutputLength') }}</h4>
              <p class="card-desc">{{ $t('settings.security.maxOutputLengthDesc') }}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="input-group">
            <input
              v-model.number="localConfig.max_output_length"
              type="number"
              min="100"
              max="1000000"
              step="1000"
              class="number-input"
              @input="handleChange"
            />
            <span class="input-suffix">{{ $t('settings.security.characters') }}</span>
          </div>
          <p class="input-hint">{{ $t('settings.security.maxOutputLengthHint') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import {
  Lock as LockIcon,
  ListChecks as ListChecksIcon,
  AlertTriangle as AlertTriangleIcon,
  FileText as FileTextIcon,
  FolderLock as FolderLockIcon,
  Clock as ClockIcon,
  Maximize as MaximizeIcon,
  ChevronDown as ChevronDownIcon,
  ChevronUp as ChevronUpIcon,
  Plus as PlusIcon,
  X as XIcon,
  Info as InfoIcon
} from 'lucide-vue-next'
import { useSettingsStore } from '@/store/settings'
import type { SecurityConfig } from '@/store/settings'
import apiClient from '@/api/client'

const settingsStore = useSettingsStore()

const localConfig = ref<SecurityConfig>({
  api_key_encryption_enabled: false,
  dangerous_commands_blocked: true,
  custom_deny_patterns: [],
  command_whitelist_enabled: false,
  custom_allow_patterns: [],
  audit_log_enabled: true,
  command_timeout: 30,
  max_output_length: 10000,
  restrict_to_workspace: true
})

const expandedSections = ref({
  denyPatterns: false,
  allowPatterns: false
})

const builtInDangerousPatterns = ref<Array<{pattern: string, description: string, key: string}>>([])

// 初始化时加载配置和内置模式
onMounted(async () => {
  if (settingsStore.settings?.security) {
    localConfig.value = { ...settingsStore.settings.security }
  }
  
  // 加载内置危险模式
  try {
    const response = await apiClient.get('/settings/security/dangerous-patterns')
    console.log('Dangerous patterns response:', response)
    if (response.success) {
      builtInDangerousPatterns.value = response.patterns
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
  { deep: true }
)

const handleChange = () => {
  settingsStore.updateSecurity(localConfig.value)
}

const addDenyPattern = () => {
  localConfig.value.custom_deny_patterns.push('')
  handleChange()
}

const removeDenyPattern = (index: number) => {
  localConfig.value.custom_deny_patterns.splice(index, 1)
  handleChange()
}

const addAllowPattern = () => {
  localConfig.value.custom_allow_patterns.push('')
  handleChange()
}

const removeAllowPattern = (index: number) => {
  localConfig.value.custom_allow_patterns.splice(index, 1)
  handleChange()
}
</script>

<style scoped>
.security-config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
  padding: var(--spacing-md);
}

.section-header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.section-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
  line-height: var(--line-height-relaxed);
}

.security-options {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.security-card {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: all var(--transition-base);
}

.security-card:hover {
  border-color: var(--color-border-secondary);
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--spacing-lg);
  gap: var(--spacing-md);
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  flex: 1;
  min-width: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}

.icon {
  flex-shrink: 0;
  color: var(--color-primary);
  margin-top: 2px;
}

.icon-warning {
  color: var(--color-warning);
}

.icon-success {
  color: var(--color-success);
}

.icon-info {
  color: var(--color-info);
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  flex: 1;
  min-width: 0;
}

.card-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0;
}

.card-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
  line-height: var(--line-height-normal);
}

/* Toggle Switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
  cursor: pointer;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--color-border-secondary);
  border: 1px solid transparent;
  border-radius: var(--radius-full);
  transition: all var(--transition-base);
}

.toggle-slider:before {
  content: '';
  position: absolute;
  height: 18px;
  width: 18px;
  left: 2px;
  bottom: 2px;
  background-color: white;
  border-radius: 50%;
  transition: all var(--transition-base);
  box-shadow: var(--shadow-sm);
}

.toggle-switch input:checked + .toggle-slider {
  background-color: var(--color-success, #10b981);
  border-color: var(--color-success, #10b981);
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(20px);
}

.toggle-switch:hover .toggle-slider {
  opacity: 0.9;
}

/* 深色模式开关 */
:root[data-theme="dark"] .toggle-slider {
  background-color: #1e2d45;
  border-color: #243050;
}

:root[data-theme="dark"] .toggle-slider:before {
  background-color: #7a9ab0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
}

:root[data-theme="dark"] .toggle-switch input:checked + .toggle-slider {
  background-color: rgba(0, 240, 255, 0.15);
  border-color: #00f0ff;
}

:root[data-theme="dark"] .toggle-switch input:checked + .toggle-slider:before {
  background-color: #00f0ff;
  box-shadow: 0 0 6px rgba(0, 240, 255, 0.3);
}

/* Expand Button */
.expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.expand-btn:hover {
  background: var(--color-bg-secondary);
  border-color: var(--color-border-secondary);
  color: var(--color-text-primary);
}

/* Card Body */
.card-body {
  border-top: 1px solid var(--color-border-primary);
  padding: var(--spacing-lg);
  background: var(--color-bg-secondary);
}

.patterns-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.built-in-patterns,
.custom-patterns {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 20px;
  padding: 0 6px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.readonly-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  background: var(--color-bg-tertiary);
  color: var(--color-text-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  flex-shrink: 0;
}

.patterns-list.readonly {
  max-height: 200px;
  overflow-y: auto;
}

/* 模式卡片网格 */
.patterns-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-sm);
}

.pattern-card {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  transition: all var(--transition-base);
  overflow: hidden;
}

.pattern-card:hover {
  border-color: var(--color-border-secondary);
  box-shadow: var(--shadow-sm);
}

.pattern-card.builtin {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.03) 0%, rgba(220, 38, 38, 0.03) 100%);
  border-left: 3px solid var(--color-error);
}

.pattern-card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
}

.pattern-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.pattern-icon.danger {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-error);
}

.pattern-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.pattern-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  line-height: var(--line-height-tight);
}

.pattern-code {
  font-size: var(--font-size-xs);
  font-family: var(--font-family-mono);
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pattern-item.readonly {
  opacity: 0.8;
}

.pattern-input.readonly {
  background: var(--color-bg-tertiary);
  cursor: default;
  color: var(--color-text-secondary);
}

.pattern-input.readonly:hover {
  border-color: var(--color-border-primary);
}

.patterns-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
}

.patterns-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.add-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 6px 12px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.add-btn:hover {
  background: var(--color-primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.add-btn:active {
  transform: translateY(0);
}

.patterns-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.pattern-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.pattern-input {
  flex: 1;
  padding: 10px 12px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-family: var(--font-family-mono);
  color: var(--color-text-primary);
  transition: all var(--transition-base);
}

.pattern-input:hover {
  border-color: var(--color-border-secondary);
}

.pattern-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-alpha);
}

.pattern-input::placeholder {
  color: var(--color-text-tertiary);
  font-family: var(--font-family-mono);
}

.remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: all var(--transition-base);
  flex-shrink: 0;
}

.remove-btn:hover {
  background: var(--color-error-light);
  border-color: var(--color-error);
  color: var(--color-error);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-lg);
  background: var(--color-bg-primary);
  border: 1px dashed var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  font-style: italic;
}

/* Expand Transition */
.expand-enter-active,
.expand-leave-active {
  transition: all var(--transition-base);
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 500px;
}

/* Input Group */
.input-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.number-input {
  flex: 1;
  padding: 10px 12px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  transition: all var(--transition-base);
  min-width: 100px;
}

.number-input:hover {
  border-color: var(--color-border-secondary);
}

.number-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-alpha);
}

.input-suffix {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
}

.input-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin: var(--spacing-sm) 0 0 0;
  line-height: var(--line-height-normal);
}
</style>
