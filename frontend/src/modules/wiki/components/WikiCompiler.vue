<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="close">
      <div class="modal-container">
        <div class="modal-header">
          <h3>AI 编译</h3>
          <button class="close-btn" @click="close">
            <XIcon :size="20" />
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>原始内容</label>
            <textarea
              v-model="form.content"
              rows="10"
              placeholder="粘贴原始内容，AI 会自动编译为结构化的知识条目"
            ></textarea>
          </div>
          <div class="form-group">
            <label>来源类型</label>
            <select v-model="form.sourceType">
              <option value="article">文章</option>
              <option value="documentation">文档</option>
              <option value="notes">笔记</option>
              <option value="conversation">对话</option>
            </select>
          </div>
          <div class="form-group">
            <label>标题提示（可选）</label>
            <input v-model="form.titleHint" type="text" placeholder="建议的标题方向">
          </div>

          <!-- 编译结果 -->
          <div v-if="result" class="compile-result">
            <h4>编译结果</h4>
            <div class="result-preview">
              <h5>{{ result.title }}</h5>
              <div class="tags" v-if="result.tags?.length">
                <span v-for="tag in result.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
              <pre>{{ result.content }}</pre>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="cancel-btn" @click="close">取消</button>
          <button
            v-if="!result"
            class="compile-btn"
            :disabled="!form.content || compiling"
            @click="handleCompile"
          >
            <LoaderIcon v-if="compiling" :size="16" class="spin" />
            <SparklesIcon v-else :size="16" />
            {{ compiling ? '编译中...' : '开始编译' }}
          </button>
          <template v-else>
            <button class="use-btn" @click="useResult">
              <EditIcon :size="16" />
              编辑后保存
            </button>
            <button class="save-btn" :disabled="saving" @click="saveDirectly">
              <LoaderIcon v-if="saving" :size="16" class="spin" />
              <CheckIcon v-else :size="16" />
              {{ saving ? '保存中...' : '直接保存' }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { X as XIcon, Sparkles as SparklesIcon, Loader2 as LoaderIcon, Check as CheckIcon, Edit as EditIcon } from 'lucide-vue-next'
import { wikiApi } from '../services/wikiApi'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits(['update:modelValue', 'result'])

const form = ref({
  content: '',
  sourceType: 'article',
  titleHint: ''
})

const compiling = ref(false)
const saving = ref(false)
const result = ref<any>(null)

const close = () => {
  emit('update:modelValue', false)
  form.value = { content: '', sourceType: 'article', titleHint: '' }
  result.value = null
}

const handleCompile = async () => {
  compiling.value = true
  try {
    const data = await wikiApi.compile({
      content: form.value.content,
      source_type: form.value.sourceType,
      title_hint: form.value.titleHint || undefined
    })
    result.value = data
  } catch (err: any) {
    alert(err.message || '编译失败')
  } finally {
    compiling.value = false
  }
}

const useResult = () => {
  emit('result', result.value)
  close()
}

const saveDirectly = async () => {
  if (!result.value) return

  try {
    saving.value = true
    await wikiApi.createEntry({
      title: result.value.title,
      content: result.value.content,
      tags: result.value.tags || []
    })
    alert('保存成功！')
    close()
    // 通知父组件刷新列表
    window.location.reload()
  } catch (err: any) {
    alert(err.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--spacing-lg);
}

.modal-container {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 700px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.close-btn {
  padding: var(--spacing-sm);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-md);
}

.close-btn:hover {
  background: var(--bg-secondary);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
}

.form-group {
  margin-bottom: var(--spacing-md);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-xs);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--font-size-base);
}

.form-group input:focus,
.form-group textarea:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-group textarea {
  resize: vertical;
}

.compile-result {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}

.compile-result h4 {
  margin: 0 0 var(--spacing-sm) 0;
  font-size: var(--font-size-base);
}

.result-preview h5 {
  margin: 0 0 var(--spacing-xs) 0;
  font-size: var(--font-size-lg);
}

.result-preview .tags {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-sm);
}

.result-preview .tag {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  font-size: var(--font-size-xs);
}

.result-preview pre {
  white-space: pre-wrap;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-lg);
  border-top: 1px solid var(--border-color);
}

.cancel-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
}

.compile-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-md);
  background: var(--color-success);
  color: white;
  cursor: pointer;
}

.compile-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.save-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: white;
  cursor: pointer;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.use-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
}

.use-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin {
  animation: spin 1s linear infinite;
}
</style>
