<template>
  <div class="mcp-editor" v-if="server">
    <!-- Editor Mode Switch -->
    <div class="editor-mode-bar">
      <div class="mode-switch">
        <button class="mode-btn" :class="{ active: editorMode === 'form' }" @click="switchMode('form')">
          {{ $t('settings.mcp.formMode') }}
        </button>
        <button class="mode-btn" :class="{ active: editorMode === 'json' }" @click="switchMode('json')">
          {{ $t('settings.mcp.jsonMode') }}
        </button>
      </div>
    </div>

    <!-- Form Mode -->
    <template v-if="editorMode === 'form'">
      <div class="mcp-field">
        <label class="mcp-field-label">{{ $t('settings.mcp.serverNamePlaceholder') }}</label>
        <input v-model="server.name" class="mcp-input" :placeholder="$t('settings.mcp.serverNamePlaceholder')" />
      </div>

      <div class="mcp-field">
        <label class="mcp-field-label">{{ $t('settings.mcp.description') }}</label>
        <input v-model="server.description" class="mcp-input" :placeholder="$t('settings.mcp.descriptionPlaceholder')" />
      </div>

      <div class="mcp-field">
        <label class="mcp-field-label">{{ $t('settings.mcp.transport') }}</label>
        <select v-model="server.transport" class="mcp-input mcp-select">
          <option value="stdio">stdio</option>
          <option value="sse">SSE</option>
          <option value="streamable_http">Streamable HTTP</option>
        </select>
      </div>

      <div v-if="showStdioFields" class="mcp-editor-group">
        <div class="mcp-field">
          <label class="mcp-field-label">{{ $t('settings.mcp.command') }}</label>
          <input v-model="server.command" class="mcp-input" placeholder="npx" />
        </div>
        <div class="mcp-field">
          <label class="mcp-field-label">{{ $t('settings.mcp.args') }}</label>
          <input
            :value="server.args.join(' ')"
            @input="server.args = ($event.target as HTMLInputElement).value.split(/\s+/).filter(Boolean)"
            class="mcp-input"
            placeholder="-y @modelcontextprotocol/server-filesystem /path"
          />
        </div>
        <div class="mcp-field">
          <label class="mcp-field-label">{{ $t('settings.mcp.env') }}</label>
          <div v-for="(_, key) in server.env" :key="key" class="mcp-kv-row">
            <input :value="key" class="mcp-input mcp-kv-key" readonly />
            <input v-model="server.env[key]" class="mcp-input mcp-kv-val" />
            <button class="mcp-kv-remove" @click="delete server.env[key]">×</button>
          </div>
          <button class="mcp-kv-add" @click="addEnv">+ {{ $t('settings.mcp.addEnv') }}</button>
        </div>
      </div>

      <div v-if="showHttpFields" class="mcp-editor-group">
        <div class="mcp-field">
          <label class="mcp-field-label">URL</label>
          <input v-model="server.url" class="mcp-input" placeholder="https://example.com/mcp/" />
        </div>
        <div class="mcp-field">
          <label class="mcp-field-label">{{ $t('settings.mcp.headers') }}</label>
          <div v-for="(_, key) in server.headers" :key="key" class="mcp-kv-row">
            <input :value="key" class="mcp-input mcp-kv-key" readonly />
            <input v-model="server.headers[key]" class="mcp-input mcp-kv-val" />
            <button class="mcp-kv-remove" @click="delete server.headers[key]">×</button>
          </div>
          <button class="mcp-kv-add" @click="addHeader">+ {{ $t('settings.mcp.addHeader') }}</button>
        </div>
      </div>

      <div class="mcp-editor-row">
        <div class="mcp-field">
          <label class="mcp-field-label">{{ $t('settings.mcp.timeout') }}</label>
          <input v-model.number="server.timeout" type="number" class="mcp-input" min="5" max="300" />
        </div>
        <div class="mcp-field">
          <label class="mcp-field-label">{{ $t('settings.mcp.connectTimeout') }}</label>
          <input v-model.number="server.connect_timeout" type="number" class="mcp-input" min="5" max="60" />
        </div>
      </div>

      <div class="mcp-field">
        <label class="mcp-field-label">{{ $t('settings.mcp.includeTools') }}</label>
        <input
          :value="server.include_tools.join(', ')"
          @input="server.include_tools = ($event.target as HTMLInputElement).value.split(',').map(s => s.trim()).filter(Boolean)"
          class="mcp-input"
          :placeholder="$t('settings.mcp.includeToolsPlaceholder')"
        />
      </div>

      <div class="mcp-field">
        <label class="mcp-field-label">{{ $t('settings.mcp.excludeTools') }}</label>
        <input
          :value="server.exclude_tools.join(', ')"
          @input="server.exclude_tools = ($event.target as HTMLInputElement).value.split(',').map(s => s.trim()).filter(Boolean)"
          class="mcp-input"
          :placeholder="$t('settings.mcp.excludeToolsPlaceholder')"
        />
      </div>

      <div class="mcp-editor-row">
        <label class="mcp-checkbox">
          <input type="checkbox" v-model="server.enable_resources" />
          <span>{{ $t('settings.mcp.enableResources') }}</span>
        </label>
        <label class="mcp-checkbox">
          <input type="checkbox" v-model="server.enable_prompts" />
          <span>{{ $t('settings.mcp.enablePrompts') }}</span>
        </label>
      </div>
    </template>

    <!-- JSON Mode -->
    <template v-else>
      <div class="mcp-json-editor-inline">
        <div v-if="jsonError" class="mcp-json-error">{{ jsonError }}</div>
        <textarea
          v-model="jsonText"
          @input="onJsonInput"
          class="mcp-textarea"
          spellcheck="false"
          :placeholder="$t('settings.mcp.jsonHint')"
        />
      </div>
    </template>

    <!-- Test Row -->
    <div class="mcp-test-row">
      <button class="mcp-btn" @click="$emit('test', server)" :disabled="testing">
        {{ testing ? $t('settings.mcp.testing') : $t('settings.mcp.testConnection') }}
      </button>
      <span v-if="testResult" class="mcp-test-msg" :class="testResult.success ? 'mcp-test-msg--success' : 'mcp-test-msg--error'">
        {{ testResult.message }}
      </span>
    </div>

    <!-- Actions -->
    <div class="mcp-editor-actions" v-if="showActions">
      <button class="mcp-btn mcp-btn-primary" @click="handleSave" :disabled="saving || !!jsonError">
        {{ saving ? $t('settings.mcp.saving') : $t('settings.mcp.save') }}
      </button>
      <button class="mcp-btn" @click="$emit('cancel')">{{ $t('settings.mcp.cancel') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { McpServerConfig, McpServerTestResult } from '@/modules/mcp/types'

const props = defineProps<{
  server: McpServerConfig | null
  testing?: boolean
  saving?: boolean
  testResult?: McpServerTestResult | null
  showActions?: boolean
}>()

const emit = defineEmits<{
  test: [server: McpServerConfig]
  save: [server: McpServerConfig]
  cancel: []
}>()

const editorMode = ref<'form' | 'json'>('form')
const jsonText = ref('')
const jsonError = ref('')

const SYNC_FIELDS = [
  'name', 'description', 'transport', 'command', 'url',
  'timeout', 'connect_timeout', 'enable_resources', 'enable_prompts',
] as const

const ARRAY_FIELDS = ['args', 'include_tools', 'exclude_tools'] as const
const RECORD_FIELDS = ['env', 'headers'] as const

function serverToJson(srv: McpServerConfig): string {
  const obj: Record<string, unknown> = {}
  for (const k of SYNC_FIELDS) {
    obj[k] = srv[k]
  }
  for (const k of ARRAY_FIELDS) {
    obj[k] = srv[k]
  }
  for (const k of RECORD_FIELDS) {
    obj[k] = srv[k]
  }
  return JSON.stringify(obj, null, 2)
}

function applyJsonToServer(parsed: Record<string, unknown>, srv: McpServerConfig) {
  for (const k of SYNC_FIELDS) {
    if (k in parsed) {
      (srv as any)[k] = parsed[k] ?? srv[k]
    }
  }
  for (const k of ARRAY_FIELDS) {
    if (k in parsed && Array.isArray(parsed[k])) {
      (srv as any)[k] = [...(parsed[k] as string[])]
    }
  }
  for (const k of RECORD_FIELDS) {
    if (k in parsed && parsed[k] && typeof parsed[k] === 'object') {
      (srv as any)[k] = { ...(parsed[k] as Record<string, string>) }
    }
  }
}

function switchMode(mode: 'form' | 'json') {
  if (mode === editorMode.value) return

  if (mode === 'json') {
    if (props.server) {
      jsonText.value = serverToJson(props.server)
      jsonError.value = ''
    }
  } else {
    if (props.server && jsonText.value) {
      try {
        const parsed = JSON.parse(jsonText.value)
        applyJsonToServer(parsed, props.server)
        jsonError.value = ''
      } catch {
        // If JSON is invalid, keep the server as-is
      }
    }
  }

  editorMode.value = mode
}

watch(() => props.server, (newServer) => {
  if (newServer && editorMode.value === 'json') {
    jsonText.value = serverToJson(newServer)
    jsonError.value = ''
  }
}, { immediate: true })

const showStdioFields = computed(() => {
  if (!props.server) return false
  return props.server.transport === 'stdio' || (!props.server.transport && !!props.server.command)
})

const showHttpFields = computed(() => {
  if (!props.server) return false
  const tr = props.server.transport
  return tr === 'streamable_http' || tr === 'sse' || (!tr && !!props.server.url)
})

function onJsonInput() {
  try {
    const parsed = JSON.parse(jsonText.value)
    jsonError.value = ''
    if (props.server) {
      applyJsonToServer(parsed, props.server)
    }
  } catch (e: any) {
    jsonError.value = e.message
  }
}

function handleSave() {
  if (editorMode.value === 'json') {
    try {
      JSON.parse(jsonText.value)
      jsonError.value = ''
    } catch (e: any) {
      jsonError.value = e.message
      return
    }
  }
  if (props.server) {
    emit('save', props.server)
  }
}

function addEnv() {
  if (!props.server) return
  const key = prompt('Environment variable name:')
  if (key) props.server.env[key.trim()] = ''
}

function addHeader() {
  if (!props.server) return
  const key = prompt('Header name:')
  if (key) props.server.headers[key.trim()] = ''
}
</script>

<style>
@import '../styles/mcp.css';

.editor-mode-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.mcp-json-editor-inline {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mcp-json-editor-inline .mcp-textarea {
  min-height: 300px;
}
</style>
