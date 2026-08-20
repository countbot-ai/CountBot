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
            <SwitchToggle
              v-model="localConfig.dangerous_commands_blocked"
              :width="44"
              :height="24"
              :aria-label="$t('settings.security.dangerousCommands')"
              @change="handleChange"
            />
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
                    v-for="(_, index) in localConfig.custom_deny_patterns"
                    :key="`deny-${index}`"
                    class="pattern-item"
                  >
                    <input
                      v-model="localConfig.custom_deny_patterns[index]"
                      type="text"
                      class="pattern-input"
                      :placeholder="$t('settings.security.patternPlaceholder')"
                      @change="handleChange"
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
            <SwitchToggle
              v-model="localConfig.command_whitelist_enabled"
              :width="44"
              :height="24"
              :aria-label="$t('settings.security.commandWhitelist')"
              @change="handleChange"
            />
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
                    v-for="(_, index) in localConfig.custom_allow_patterns"
                  :key="`allow-${index}`"
                  class="pattern-item"
                >
                  <input
                    v-model="localConfig.custom_allow_patterns[index]"
                    type="text"
                    class="pattern-input"
                    :placeholder="$t('settings.security.patternPlaceholder')"
                    @change="handleChange"
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
          <SwitchToggle
            v-model="localConfig.audit_log_enabled"
            :width="44"
            :height="24"
            :aria-label="$t('settings.security.auditLog')"
            @change="handleChange"
          />
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
          <SwitchToggle
            v-model="localConfig.restrict_to_workspace"
            :width="44"
            :height="24"
            :aria-label="$t('settings.workspace.isolation')"
            @change="handleChange"
          />
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
              min="10"
              max="1800"
              class="number-input"
              @input="handleChange"
            />
            <span class="input-suffix">{{ $t('settings.security.seconds') }}</span>
          </div>
          <p class="input-hint">{{ $t('settings.security.commandTimeoutHint') }}</p>
        </div>
      </div>

      <!-- Subagent Timeout -->
      <div class="security-card">
        <div class="card-header">
          <div class="header-left">
            <component
              :is="ClockIcon"
              :size="20"
              class="icon icon-info"
            />
            <div class="header-text">
              <h4 class="card-title">{{ $t('settings.security.subagentTimeout') }}</h4>
              <p class="card-desc">{{ $t('settings.security.subagentTimeoutDesc') }}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          <div class="input-group">
            <input
              v-model.number="localConfig.subagent_timeout"
              type="number"
              min="60"
              max="3600"
              step="60"
              class="number-input"
              @input="handleChange"
            />
            <span class="input-suffix">{{ $t('settings.security.seconds') }}</span>
          </div>
          <p class="input-hint">{{ $t('settings.security.subagentTimeoutHint') }}</p>
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
import SwitchToggle from '@/components/ui/SwitchToggle.vue'

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
  restrict_to_workspace: false
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
  { deep: true }
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
@import './styles/SecurityConfig.css';
</style>
