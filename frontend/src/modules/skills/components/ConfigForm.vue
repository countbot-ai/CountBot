<template>
  <div class="config-form">
    <template v-for="segment in segments" :key="segment.key">
      <div v-if="segment.type === 'fields'" class="config-group">
        <ConfigFieldInput
          v-for="field in segment.fields"
          :key="field.key"
          :field="field"
          :model-value="values[field.key]"
          @update:model-value="(val) => handleUpdate(field.key, val)"
        />
      </div>

      <section v-else class="config-tabs-section">
        <div class="config-tabs" role="tablist" aria-label="配置分组">
          <button
            v-for="field in segment.fields"
            :key="field.key"
            type="button"
            class="config-tab"
            :class="{ active: getActiveTab(segment.key, segment.fields) === field.key }"
            @click="setActiveTab(segment.key, field.key)"
          >
            <span class="config-tab-title">{{ field.label }}</span>
            <span class="config-tab-meta">{{ getTabMeta(field) }}</span>
            <span
              class="config-tab-status"
              :class="{ configured: isConfiguredField(field) }"
            >
              {{ isConfiguredField(field) ? '已配置' : '待填写' }}
            </span>
          </button>
        </div>

        <div class="config-tab-panel">
          <ConfigFieldInput
            v-if="getActiveField(segment.key, segment.fields)"
            :field="getActiveField(segment.key, segment.fields)!"
            :model-value="values[getActiveField(segment.key, segment.fields)!.key]"
            :force-expanded="true"
            @update:model-value="(val) => handleUpdate(getActiveField(segment.key, segment.fields)!.key, val)"
          />
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ConfigFieldInput from './ConfigFieldInput.vue'
import type { ConfigFieldSchema } from '@/api/endpoints'

interface Props {
  fields: ConfigFieldSchema[]
  values: Record<string, any>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update', key: string, value: any): void
}>()

type ConfigSegment = {
  key: string
  type: 'fields' | 'object-tabs'
  fields: ConfigFieldSchema[]
}

const activeTabs = ref<Record<string, string>>({})

const segments = computed<ConfigSegment[]>(() => {
  const result: ConfigSegment[] = []
  let scalarBuffer: ConfigFieldSchema[] = []
  let objectBuffer: ConfigFieldSchema[] = []

  const flushScalar = () => {
    if (!scalarBuffer.length) return
    result.push({
      key: `fields:${scalarBuffer.map(field => field.key).join('|')}`,
      type: 'fields',
      fields: scalarBuffer
    })
    scalarBuffer = []
  }

  const flushObjects = () => {
    if (!objectBuffer.length) return

    if (objectBuffer.length >= 2) {
      result.push({
        key: `tabs:${objectBuffer.map(field => field.key).join('|')}`,
        type: 'object-tabs',
        fields: objectBuffer
      })
    } else {
      result.push({
        key: `fields:${objectBuffer[0].key}`,
        type: 'fields',
        fields: [...objectBuffer]
      })
    }

    objectBuffer = []
  }

  for (const field of props.fields) {
    if (field.type === 'object') {
      flushScalar()
      objectBuffer.push(field)
    } else {
      flushObjects()
      scalarBuffer.push(field)
    }
  }

  flushObjects()
  flushScalar()

  return result
})

const getPreferredTabKey = (fields: ConfigFieldSchema[]) => {
  const defaultMailbox = props.values.default_mailbox
  if (typeof defaultMailbox === 'string') {
    const mailboxKey = `${defaultMailbox}_email`
    if (fields.some(field => field.key === mailboxKey)) {
      return mailboxKey
    }
    if (fields.some(field => field.key === defaultMailbox)) {
      return defaultMailbox
    }
  }
  return fields[0]?.key ?? ''
}

watch(
  [segments, () => props.values.default_mailbox],
  ([nextSegments]) => {
    const nextTabs: Record<string, string> = { ...activeTabs.value }
    for (const segment of nextSegments) {
      if (segment.type !== 'object-tabs') continue
      const current = nextTabs[segment.key]
      if (!current || !segment.fields.some(field => field.key === current)) {
        nextTabs[segment.key] = getPreferredTabKey(segment.fields)
        continue
      }

      const preferred = getPreferredTabKey(segment.fields)
      if (preferred && preferred !== current && segment.fields.some(field => field.key === preferred)) {
        nextTabs[segment.key] = preferred
      }
    }
    activeTabs.value = nextTabs
  },
  { immediate: true }
)

const handleUpdate = (key: string, value: any) => {
  emit('update', key, value)
}

const setActiveTab = (segmentKey: string, fieldKey: string) => {
  activeTabs.value = {
    ...activeTabs.value,
    [segmentKey]: fieldKey
  }
}

const getActiveTab = (segmentKey: string, fields: ConfigFieldSchema[]) => {
  return activeTabs.value[segmentKey] || getPreferredTabKey(fields)
}

const getActiveField = (segmentKey: string, fields: ConfigFieldSchema[]) => {
  const activeKey = getActiveTab(segmentKey, fields)
  return fields.find(field => field.key === activeKey) || fields[0] || null
}

const isConfiguredField = (field: ConfigFieldSchema) => {
  const value = props.values[field.key]
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }

  const requiredFields = field.fields?.filter(subField => subField.required) ?? []
  if (!requiredFields.length) {
    return Object.values(value).some(item => item !== undefined && item !== null && String(item).trim() !== '')
  }

  return requiredFields.every(subField => {
    const item = value[subField.key]
    return item !== undefined && item !== null && String(item).trim() !== ''
  })
}

const getTabMeta = (field: ConfigFieldSchema) => {
  const value = props.values[field.key]
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    if (typeof value.email === 'string' && value.email.trim()) {
      return value.email.trim()
    }

    const protocol = typeof value.receive_protocol === 'string' ? value.receive_protocol.toUpperCase() : ''
    const host = value.imap_server || value.pop_server || value.smtp_server
    if (protocol && host) {
      return `${protocol} · ${host}`
    }
    if (protocol) {
      return protocol
    }
    if (typeof host === 'string' && host.trim()) {
      return host.trim()
    }
  }

  return field.description || '点击查看配置'
}
</script>

<style scoped>
.config-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.config-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.config-tabs-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.config-tabs {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--spacing-sm);
}

.config-tab {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.92) 100%);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  transition: transform var(--transition-base), border-color var(--transition-base), box-shadow var(--transition-base);
}

.config-tab:hover {
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.35);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.config-tab.active {
  border-color: var(--color-primary);
  box-shadow: 0 14px 28px rgba(59, 130, 246, 0.16);
}

.config-tab-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.config-tab-meta {
  min-height: 18px;
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  line-height: 1.45;
}

.config-tab-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: var(--font-weight-medium);
}

.config-tab-status.configured {
  background: rgba(16, 185, 129, 0.14);
  color: #059669;
}

.config-tab-panel {
  padding: var(--spacing-sm) 0 0;
}

:root[data-theme="dark"] .config-tab {
  background: linear-gradient(180deg, rgba(10, 14, 26, 0.96) 0%, rgba(12, 18, 32, 0.9) 100%);
  border-color: #1f2b44;
}

:root[data-theme="dark"] .config-tab:hover {
  border-color: rgba(0, 240, 255, 0.26);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.28);
}

:root[data-theme="dark"] .config-tab.active {
  border-color: rgba(0, 240, 255, 0.4);
  box-shadow: 0 12px 28px rgba(0, 240, 255, 0.12);
}

:root[data-theme="dark"] .config-tab-status {
  background: rgba(148, 163, 184, 0.18);
  color: #cbd5e1;
}

:root[data-theme="dark"] .config-tab-status.configured {
  background: rgba(16, 185, 129, 0.18);
  color: #34d399;
}

@media (max-width: 768px) {
  .config-tabs {
    grid-template-columns: 1fr;
  }
}
</style>
