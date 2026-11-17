<template>
  <section class="hs-shell">
    <header v-if="hasOwnHead" class="hs-head">
      <div class="hs-head-text">
        <h1 class="hs-title">{{ title }}</h1>
        <p class="hs-desc">{{ description }}</p>
      </div>

      <div class="hs-head-actions">
        <template v-if="section === 'persona'">
          <button
            class="hs-btn hs-btn--primary"
            :disabled="personaSaving"
            @click="savePersona"
          >
            {{ personaSaving ? $t('common.saving') : $t('common.save') }}
          </button>
        </template>

        <template v-else-if="section === 'channels'">
          <span v-if="channelsDirty" class="hs-dirty">
            <span class="hs-dirty-dot" />
            {{ $t('settings.saveState.dirty') }}
          </span>
          <button
            class="hs-btn hs-btn--primary"
            :disabled="channelsSaving || !channelsDirty"
            @click="saveChannels"
          >
            {{ channelsSaving ? $t('common.saving') : $t('common.save') }}
          </button>
        </template>
      </div>
    </header>

    <div class="hs-body" :class="{ 'is-flush': isFlush }">
      <CronManager v-if="section === 'cron'" />

      <div v-else-if="section === 'skills' || section === 'wiki'" class="hs-fill">
        <SkillsLibrary v-if="section === 'skills'" />
        <WikiPanel v-else />
      </div>

      <div v-else-if="waiting" class="hs-state">{{ $t('common.loading') }}</div>

      <div
        v-else
        class="hs-inner"
        :class="{
          'is-narrow': section === 'persona',
          'is-wide': section === 'channels' || section === 'multiagent',
        }"
      >
        <MultiAgentConfig v-if="section === 'multiagent'" />
        <ChannelsConfig v-else-if="section === 'channels'" />
        <template v-else-if="section === 'persona'">
          <PersonaConfig ref="personaRef" />
        </template>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/store/settings'
import { useChannelsStore } from '@/store/channels'
import { useUserStore } from '@/store/user'
import { useToast } from '@/composables/useToast'
import type { ChatSection } from '@/modules/chat/next/types'

// 六个业务页都比较重，按需加载，避免拖慢首页首屏
const CronManager = defineAsyncComponent(() => import('@/modules/scheduler/CronManager.vue'))
const SkillsLibrary = defineAsyncComponent(() => import('@/modules/skills/SkillsLibrary.vue'))
const WikiPanel = defineAsyncComponent(() => import('@/modules/wiki/WikiPanel.vue'))
const MultiAgentConfig = defineAsyncComponent(() => import('@/modules/settings/MultiAgentConfig.vue'))
const ChannelsConfig = defineAsyncComponent(() => import('@/modules/settings/ChannelsConfig.vue'))
const PersonaConfig = defineAsyncComponent(() => import('@/modules/settings/PersonaConfig.vue'))

type Section = Exclude<ChatSection, 'sessions'>

const props = defineProps<{ section: Section }>()

const { t } = useI18n()
const toast = useToast()
const userStore = useUserStore()
const settingsStore = useSettingsStore()
const channelsStore = useChannelsStore()

/** 定时任务自带标题与操作区；技能库 / 知识库的页头下还要接它们自己的表签栏 */
const hasOwnHead = computed(() => props.section !== 'cron')
const isFlush = computed(() =>
  ['cron', 'skills', 'wiki'].includes(props.section),
)

const title = computed(() => {
  const titles: Record<Section, string> = {
    cron: t('cron.title'),
    skills: t('nav.skills'),
    wiki: t('nav.wiki'),
    multiagent: t('nav.multiagent'),
    channels: t('nav.remoteConnection'),
    persona: t('nav.persona'),
  }
  return titles[props.section]
})

const description = computed(() => {
  const descs: Record<Section, string> = {
    cron: t('cron.description'),
    skills: t('home.sections.skillsDesc'),
    wiki: t('home.sections.wikiDesc'),
    multiagent: t('settings.tabDesc.multiagent'),
    channels: t('settings.tabDesc.channels'),
    persona: t('settings.tabDesc.persona'),
  }
  return descs[props.section]
})

// 性格页需要全局人设配置，其余页面自取数据
const waiting = ref(false)

onMounted(async () => {
  if (props.section !== 'persona') return
  waiting.value = true
  try {
    if (!userStore.loaded) {
      await userStore.loadProfile()
    }
    if (userStore.isAdmin && !settingsStore.settings) {
      await settingsStore.loadSettings()
    }
  } catch (error) {
    console.error('[HomeSection] 人设配置加载失败:', error)
  } finally {
    waiting.value = false
  }
})

// ---------- 性格 ----------

const personaSaving = ref(false)
const personaRef = ref<{ saveConfig?: () => Promise<boolean> } | null>(null)

const savePersona = async () => {
  const api = personaRef.value
  if (personaSaving.value || !api?.saveConfig) return
  personaSaving.value = true
  try {
    await api.saveConfig()
    // 管理员的人设先写入草稿 store，需在此整体提交
    if (userStore.isAdmin && settingsStore.settings) {
      await settingsStore.saveSettings({ persona: settingsStore.settings.persona })
    }
    toast.success(t('settings.saveSuccess'), t('common.success'))
  } catch (error) {
    console.error('[HomeSection] 保存人设失败:', error)
    toast.error(t('settings.saveError'), t('common.error'))
  } finally {
    personaSaving.value = false
  }
}

// ---------- 远程连接 ----------

const channelsSaving = ref(false)
const channelsDirty = computed(() => channelsStore.hasUnsavedChanges())

const saveChannels = async () => {
  if (channelsSaving.value) return
  channelsSaving.value = true
  try {
    const saved = await channelsStore.saveAllChannels()
    if (!saved) throw new Error(channelsStore.error || 'save failed')
    toast.success(t('settings.saveSuccess'), t('common.success'))
  } catch (error) {
    console.error('[HomeSection] 保存渠道配置失败:', error)
    toast.error(t('settings.saveError'), t('common.error'))
  } finally {
    channelsSaving.value = false
  }
}
</script>

<style scoped>
@import './styles/HomeSection.css';
</style>
