<template>
  <transition name="modal">
    <div v-if="show" class="modal-overlay" @click="handleClose">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <button class="close-btn" @click="handleClose">
            <component :is="XIcon" :size="20" />
          </button>
        </div>
        
        <div class="modal-body">
          <div class="form-group">
            <label class="label">{{ $t('avatar.urlLabel') }}</label>
            <input
              v-model="avatarUrl"
              type="text"
              class="input"
              :placeholder="$t('avatar.urlPlaceholder')"
              @keydown.enter="handleSave"
            />
            <p class="hint">{{ $t('avatar.urlHint') }}</p>
          </div>

          <div v-if="avatarUrl" class="preview-section">
            <label class="label">{{ $t('avatar.preview') }}</label>
            <div class="avatar-preview">
              <img
                :src="avatarUrl"
                alt="Avatar Preview"
                class="preview-image"
                @error="handleImageError"
              />
            </div>
            <p v-if="imageError" class="error-text">{{ $t('avatar.imageError') }}</p>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="handleClear">
            {{ $t('avatar.clear') }}
          </button>
          <div class="footer-actions">
            <button class="btn btn-secondary" @click="handleClose">
              {{ $t('common.cancel') }}
            </button>
            <button
              class="btn btn-primary"
              :disabled="!avatarUrl || imageError"
              @click="handleSave"
            >
              {{ $t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { X as XIcon } from 'lucide-vue-next'

interface Props {
  show: boolean
  title: string
  currentUrl?: string
}

interface Emits {
  (e: 'update:show', value: boolean): void
  (e: 'save', url: string): void
  (e: 'clear'): void
}

const props = withDefaults(defineProps<Props>(), {
  currentUrl: ''
})

const emit = defineEmits<Emits>()

const avatarUrl = ref('')
const imageError = ref(false)

watch(() => props.show, (newVal) => {
  if (newVal) {
    avatarUrl.value = props.currentUrl || ''
    imageError.value = false
  }
})

watch(avatarUrl, () => {
  imageError.value = false
})

const handleClose = () => {
  emit('update:show', false)
}

const handleSave = () => {
  if (avatarUrl.value && !imageError.value) {
    emit('save', avatarUrl.value)
    handleClose()
  }
}

const handleClear = () => {
  emit('clear')
  handleClose()
}

const handleImageError = () => {
  imageError.value = true
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: var(--bg-primary);
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  max-height: 90vh;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}

.modal-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 20px;
}

.label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  transition: all 0.2s;
}

.input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.preview-section {
  margin-top: 20px;
}

.avatar-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.preview-image {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid var(--border-color);
}

.error-text {
  margin: 8px 0 0 0;
  font-size: 12px;
  color: var(--color-error);
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
}

.footer-actions {
  display: flex;
  gap: 12px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-primary {
  background: var(--primary-color);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-color-dark, #2563eb);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 动画 */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-active .modal-content,
.modal-leave-active .modal-content {
  transition: transform 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .modal-content,
.modal-leave-to .modal-content {
  transform: scale(0.9);
}

/* 深色主题 */
:root[data-theme="dark"] .modal-overlay {
  background: rgba(0, 0, 0, 0.7);
}
</style>
