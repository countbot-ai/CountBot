<template>
  <transition name="sidebar-slide">
    <aside
      v-if="visible"
      class="system-sidebar"
      @click.self="$emit('close')"
    >
      <div class="sidebar-panel">
        <div class="sidebar-header">
          <div class="sidebar-brand">
            <img src="@/assets/countbot-logo.svg" alt="CountBot Logo" class="sidebar-logo" />
            <h2 class="sidebar-title">{{ $t('sidebar.title') }}</h2>
          </div>
          <button
            class="close-btn"
            :title="$t('common.close')"
            @click="$emit('close')"
          >
            <component :is="XIcon" :size="18" />
          </button>
        </div>

        <div class="sidebar-body">
          <!-- 加载状态 -->
          <div v-if="loading" class="loading-state">
            <component :is="LoaderIcon" :size="20" class="spin" />
            <span>{{ $t('common.loading') }}</span>
          </div>

          <!-- 系统信息 -->
          <div v-else class="info-list">
            <!-- API 地址 -->
            <div class="info-item">
              <div class="info-label">
                <component :is="GlobeIcon" :size="16" />
                <span>{{ $t('sidebar.apiAddress') }}</span>
              </div>
              <div class="info-value api-url">
                <a
                  :href="info.api_url"
                  class="api-link"
                  @click.prevent="openApiUrl"
                >
                  {{ info.api_url }}
                </a>
                <button
                  class="copy-btn"
                  :title="$t('common.copy')"
                  @click="copyToClipboard(info.api_url)"
                >
                  <component :is="copied ? CheckIcon : CopyIcon" :size="14" />
                </button>
              </div>
            </div>

            <!-- 版本 -->
            <div class="info-item">
              <div class="info-label">
                <component :is="TagIcon" :size="16" />
                <span>{{ $t('sidebar.version') }}</span>
              </div>
              <div class="info-value">{{ info.version }}</div>
            </div>

            <!-- Python 版本 -->
            <div class="info-item">
              <div class="info-label">
                <component :is="CodeIcon" :size="16" />
                <span>Python</span>
              </div>
              <div class="info-value">{{ info.python_version }}</div>
            </div>

            <!-- 操作系统 -->
            <div class="info-item">
              <div class="info-label">
                <component :is="MonitorIcon" :size="16" />
                <span>{{ $t('sidebar.os') }}</span>
              </div>
              <div class="info-value">{{ info.os }}</div>
            </div>

            <!-- 架构 -->
            <div class="info-item">
              <div class="info-label">
                <component :is="CpuIcon" :size="16" />
                <span>{{ $t('sidebar.arch') }}</span>
              </div>
              <div class="info-value">{{ info.arch }}</div>
            </div>

            <!-- PID -->
            <div class="info-item">
              <div class="info-label">
                <component :is="HashIcon" :size="16" />
                <span>PID</span>
              </div>
              <div class="info-value">{{ info.pid }}</div>
            </div>
          </div>

          <!-- 项目信息 -->
          <div class="project-section">
            <div class="section-divider" />
            <div class="project-header">
              <h3 class="section-title">{{ $t('sidebar.projectInfo') || '项目信息' }}</h3>
            </div>
            <div class="project-links">
              <a
                href="https://github.com/countbot-ai/countbot"
                target="_blank"
                rel="noopener noreferrer"
                class="project-link"
              >
                <component :is="GithubIcon" :size="18" />
                <div class="project-link-content">
                  <span class="project-link-title">GitHub</span>
                  <span class="project-link-desc">countbot-ai/CountBot</span>
                </div>
                <component :is="ExternalLinkIcon" :size="14" class="external-icon" />
              </a>
              <a
                href="https://654321.ai"
                target="_blank"
                rel="noopener noreferrer"
                class="project-link"
              >
                <component :is="GlobeIcon" :size="18" />
                <div class="project-link-content">
                  <span class="project-link-title">{{ $t('sidebar.website') || '官网' }}</span>
                  <span class="project-link-desc">654321.ai</span>
                </div>
                <component :is="ExternalLinkIcon" :size="14" class="external-icon" />
              </a>
              <a
                href="https://654321.ai/docs/"
                target="_blank"
                rel="noopener noreferrer"
                class="project-link"
              >
                <component :is="BookOpenIcon" :size="18" />
                <div class="project-link-content">
                  <span class="project-link-title">{{ $t('sidebar.documentation') || '文档' }}</span>
                  <span class="project-link-desc">{{ $t('sidebar.readDocs') || '查看完整文档' }}</span>
                </div>
                <component :is="ExternalLinkIcon" :size="14" class="external-icon" />
              </a>
            </div>
            <div class="project-tagline">
              <p>654321, AI Delivers</p>
            </div>
          </div>

          <!-- 用户信息 & 注销（仅远程登录时显示） -->
          <div v-if="authInfo && !authInfo.is_local && authInfo.authenticated" class="auth-section">
            <div class="auth-divider" />
            <div class="auth-user">
              <div class="auth-user-icon">
                <component :is="UserIcon" :size="16" />
              </div>
              <div class="auth-user-info">
                <span class="auth-user-label">{{ $t('sidebar.remoteAccess') || '远程访问' }}</span>
                <span class="auth-user-status">{{ $t('sidebar.authenticated') || '已认证' }}</span>
              </div>
            </div>
            <button class="logout-btn" @click="handleLogout">
              <component :is="LogOutIcon" :size="16" />
              <span>{{ $t('sidebar.logout') || '注销' }}</span>
            </button>
          </div>
        </div>
      </div>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  X as XIcon,
  Loader2 as LoaderIcon,
  Globe as GlobeIcon,
  Tag as TagIcon,
  Code as CodeIcon,
  Monitor as MonitorIcon,
  Cpu as CpuIcon,
  Hash as HashIcon,
  Copy as CopyIcon,
  Check as CheckIcon,
  User as UserIcon,
  LogOut as LogOutIcon,
  Github as GithubIcon,
  ExternalLink as ExternalLinkIcon,
  BookOpen as BookOpenIcon,
} from 'lucide-vue-next'
import { systemAPI, authAPI, type SystemInfo } from '@/api/endpoints'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ visible: boolean }>()
defineEmits<{ close: [] }>()

const { t } = useI18n()
const toast = useToast()

const loading = ref(false)
const copied = ref(false)
const info = ref<SystemInfo>({
  api_url: '',
  version: '',
  python_version: '',
  os: '',
  arch: '',
  pid: 0,
  uptime_start: '',
})

const authInfo = ref<{ is_local: boolean; auth_enabled: boolean; authenticated: boolean } | null>(null)

async function fetchInfo() {
  loading.value = true
  try {
    const [sysInfo, authStatus] = await Promise.all([
      systemAPI.getInfo(),
      authAPI.status().catch(() => null),
    ])
    info.value = sysInfo
    authInfo.value = authStatus
  } catch (e) {
    console.error('Failed to load system info:', e)
    const loc = window.location
    info.value = {
      ...info.value,
      api_url: `${loc.protocol}//${loc.host}`,
    }
  } finally {
    loading.value = false
  }
}

async function handleLogout() {
  try {
    await authAPI.logout()
    localStorage.removeItem('CountBot_token')
    window.location.href = '/login'
  } catch {
    // 即使请求失败也清除本地 token 并跳转
    localStorage.removeItem('CountBot_token')
    window.location.href = '/login'
  }
}

function openApiUrl() {
  const url = info.value.api_url || `${window.location.protocol}//${window.location.host}`
  // 桌面 pywebview 环境下 window.open 可能被拦截，用 a 标签兜底
  const a = document.createElement('a')
  a.href = url
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  a.click()
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    toast.success(t('common.copied'))
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    toast.error(t('common.copyFailed'))
  }
}

watch(
  () => props.visible,
  (v) => {
    if (v) fetchInfo()
  }
)
</script>

<style scoped>
/* 遮罩 + 面板容器 */
.system-sidebar {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
}

/* 左侧面板 */
.sidebar-panel {
  width: 300px;
  max-width: 80vw;
  height: 100%;
  background: var(--bg-primary, #fff);
  border-right: 1px solid var(--border-color, #e5e7eb);
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #111827);
  margin: 0;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-logo {
  width: 32px;
  height: 32px;
  border-radius: 6px;
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all 0.15s;
}
.close-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #111827);
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* 加载 */
.loading-state {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-tertiary, #9ca3af);
  font-size: 14px;
  padding: 24px 0;
  justify-content: center;
}

.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 信息列表 */
.info-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-tertiary, #9ca3af);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.info-value {
  font-size: 14px;
  color: var(--text-primary, #111827);
  word-break: break-all;
  padding-left: 22px;
}

.info-value.api-url {
  display: flex;
  align-items: center;
  gap: 6px;
}

.api-link {
  color: var(--color-primary, #3b82f6);
  text-decoration: none;
  cursor: pointer;
  transition: color 0.15s;
}
.api-link:hover {
  text-decoration: underline;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-tertiary, #9ca3af);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}
.copy-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #111827);
}

/* 认证区域 */
.auth-section {
  margin-top: 8px;
}

.auth-divider {
  height: 1px;
  background: var(--border-color, #e5e7eb);
  margin: 16px 0;
}

.auth-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-tertiary, #f1f5f9);
  border-radius: 8px;
  margin-bottom: 12px;
}

.auth-user-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary-light, #f1f5f9);
  color: var(--color-primary, #334155);
  flex-shrink: 0;
}

.auth-user-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.auth-user-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #111827);
}

.auth-user-status {
  font-size: 11px;
  color: var(--color-success, #10b981);
}

.logout-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 9px 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  background: transparent;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.logout-btn:hover {
  color: var(--color-error, #ef4444);
  border-color: var(--color-error, #ef4444);
  background: var(--color-error-bg, #fee2e2);
}

.logout-btn:hover {
  color: var(--color-error, #ef4444);
  border-color: var(--color-error, #ef4444);
  background: var(--color-error-bg, #fee2e2);
}

/* 项目信息区域 */
.project-section {
  margin-top: 8px;
}

.section-divider {
  height: 1px;
  background: var(--border-color, #e5e7eb);
  margin: 16px 0;
}

.project-header {
  margin-bottom: 12px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary, #9ca3af);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.project-links {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.project-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-secondary, #f9fafb);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  text-decoration: none;
  color: var(--text-primary, #111827);
  transition: all 0.15s;
  cursor: pointer;
}

.project-link:hover {
  background: var(--hover-bg, #f3f4f6);
  border-color: var(--color-primary, #3b82f6);
  transform: translateX(2px);
}

.project-link-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.project-link-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #111827);
}

.project-link-desc {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.external-icon {
  color: var(--text-tertiary, #9ca3af);
  flex-shrink: 0;
  opacity: 0.5;
  transition: opacity 0.15s;
}

.project-link:hover .external-icon {
  opacity: 1;
  color: var(--color-primary, #3b82f6);
}

.project-tagline {
  padding: 12px;
  background: var(--bg-tertiary, #f1f5f9);
  border-radius: 8px;
  text-align: center;
}

.project-tagline p {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #111827);
  line-height: 1.6;
  font-style: italic;
}

/* 过渡动画 */
.sidebar-slide-enter-active,
.sidebar-slide-leave-active {
  transition: opacity 0.2s ease;
}
.sidebar-slide-enter-active .sidebar-panel,
.sidebar-slide-leave-active .sidebar-panel {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.sidebar-slide-enter-from,
.sidebar-slide-leave-to {
  opacity: 0;
}
.sidebar-slide-enter-from .sidebar-panel,
.sidebar-slide-leave-to .sidebar-panel {
  transform: translateX(-100%);
}

@media (max-width: 768px) {
  .sidebar-panel {
    width: 100%;
    max-width: 100%;
  }
}

/* 深色模式 */
:root[data-theme="dark"] .sidebar-panel {
  background: #0a0e1a;
  border-color: #152035;
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.4);
}

:root[data-theme="dark"] .sidebar-header {
  border-color: #152035;
}

:root[data-theme="dark"] .sidebar-title {
  color: #d0e8f0;
}

:root[data-theme="dark"] .close-btn {
  color: #7a9ab0;
}

:root[data-theme="dark"] .close-btn:hover {
  background: rgba(0, 240, 255, 0.06);
  color: #00f0ff;
}

:root[data-theme="dark"] .info-label {
  color: #4a6578;
}

:root[data-theme="dark"] .info-value {
  color: #d0e8f0;
}

:root[data-theme="dark"] .api-link {
  color: #00f0ff;
}

:root[data-theme="dark"] .api-link:hover {
  color: #33f5ff;
}

:root[data-theme="dark"] .copy-btn {
  color: #4a6578;
}

:root[data-theme="dark"] .copy-btn:hover {
  background: rgba(0, 240, 255, 0.06);
  color: #00f0ff;
}

:root[data-theme="dark"] .auth-divider {
  background: #152035;
}

:root[data-theme="dark"] .auth-user {
  background: #131b2c;
}

:root[data-theme="dark"] .auth-user-icon {
  background: rgba(0, 240, 255, 0.08);
  color: #00f0ff;
}

:root[data-theme="dark"] .auth-user-label {
  color: #d0e8f0;
}

:root[data-theme="dark"] .auth-user-status {
  color: #00ff88;
}

:root[data-theme="dark"] .logout-btn {
  color: #7a9ab0;
  border-color: #1e2d45;
}

:root[data-theme="dark"] .logout-btn:hover {
  color: #ff6b8a;
  border-color: rgba(255, 45, 111, 0.4);
  background: rgba(255, 45, 111, 0.08);
}

:root[data-theme="dark"] .section-divider {
  background: #152035;
}

:root[data-theme="dark"] .section-title {
  color: #4a6578;
}

:root[data-theme="dark"] .project-link {
  background: #0e1422;
  border-color: #152035;
  color: #d0e8f0;
}

:root[data-theme="dark"] .project-link:hover {
  background: #131b2c;
  border-color: #00f0ff;
}

:root[data-theme="dark"] .project-link-title {
  color: #d0e8f0;
}

:root[data-theme="dark"] .project-link-desc {
  color: #4a6578;
}

:root[data-theme="dark"] .project-link:hover .external-icon {
  color: #00f0ff;
}

:root[data-theme="dark"] .project-tagline {
  background: #131b2c;
}

:root[data-theme="dark"] .project-tagline p {
  color: #d0e8f0;
}
</style>
