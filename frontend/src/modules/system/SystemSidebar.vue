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
@import './styles/SystemSidebar.css';
</style>
