<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="modelValue" class="wf-fullscreen-modal" @click.self="close">
        <div class="wf-fullscreen-container">
          <!-- 头部控制栏 -->
          <div class="wf-fullscreen-header">
            <div class="wf-fullscreen-title">
              <component :is="NetworkIcon" :size="20" />
              <h3>多智能体工作流详情</h3>
              <span class="wf-fullscreen-count">{{ agentCount }} 个成员</span>
            </div>
            
            <div class="wf-fullscreen-controls">
              <!-- 视图切换 -->
              <div class="wf-view-switcher">
                <button
                  class="wf-view-btn"
                  :class="{ active: viewMode === 'grid' }"
                  @click="viewMode = 'grid'"
                >
                  <component :is="LayoutGridIcon" :size="16" />
                  <span>并排视图</span>
                </button>
                <button
                  class="wf-view-btn"
                  :class="{ active: viewMode === 'list' }"
                  @click="viewMode = 'list'"
                >
                  <component :is="ListIcon" :size="16" />
                  <span>列表视图</span>
                </button>
              </div>
              
              <!-- 关闭按钮 -->
              <button class="wf-close-btn" @click="close">
                <component :is="XIcon" :size="20" />
              </button>
            </div>
          </div>
          
          <!-- 内容区域 -->
          <div class="wf-fullscreen-content">
            <WorkflowComparePanel
              v-if="viewMode === 'grid'"
              :workflow-agents="workflowAgents"
            />
            <WorkflowListPanel
              v-else
              :workflow-agents="workflowAgents"
            />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { X as XIcon, Network as NetworkIcon, LayoutGrid as LayoutGridIcon, List as ListIcon } from 'lucide-vue-next'
import WorkflowComparePanel from './WorkflowComparePanel.vue'
import WorkflowListPanel from './WorkflowListPanel.vue'

interface Props {
  modelValue: boolean
  workflowAgents: Record<string, any>
}

const props = defineProps<Props>()
const emit = defineEmits(['update:modelValue'])

const viewMode = ref<'grid' | 'list'>('grid')

const agentCount = computed(() => Object.keys(props.workflowAgents || {}).length)

const close = () => {
  emit('update:modelValue', false)
}

// ESC 键关闭
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && props.modelValue) {
    close()
  }
}

// 监听键盘事件
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', handleKeydown)
}
</script>

<style scoped>
.wf-fullscreen-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  overflow: hidden;
}

.wf-fullscreen-container {
  width: 100%;
  height: 100%;
  max-width: 1800px;
  background: var(--bg-primary, #ffffff);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: modal-scale-in 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes modal-scale-in {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.wf-fullscreen-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 28px;
  background: linear-gradient(135deg, var(--bg-tertiary, #f8fafc) 0%, var(--bg-secondary, #f1f5f9) 100%);
  border-bottom: 2px solid var(--border-color, #e2e8f0);
  flex-shrink: 0;
}

.wf-fullscreen-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.wf-fullscreen-title h3 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
}

.wf-fullscreen-count {
  padding: 5px 14px;
  background: var(--bg-tertiary, #f1f5f9);
  color: var(--text-secondary, #64748b);
  font-size: 13px;
  font-weight: 600;
  border-radius: 14px;
  border: 1px solid var(--border-color, #e2e8f0);
}

.wf-fullscreen-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

.wf-view-switcher {
  display: flex;
  gap: 8px;
  padding: 4px;
  background: var(--bg-secondary, #f1f5f9);
  border-radius: 10px;
  border: 1px solid var(--border-color, #e2e8f0);
}

.wf-view-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 18px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary, #64748b);
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.wf-view-btn:hover {
  color: var(--text-primary, #1e293b);
  background: var(--bg-primary, #ffffff);
  transform: translateY(-1px);
}

.wf-view-btn.active {
  color: var(--accent-color, #3b82f6);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

.wf-close-btn {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary, #ffffff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  color: var(--text-secondary, #64748b);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.wf-close-btn:hover {
  background: #fee2e2;
  border-color: #dc2626;
  color: #dc2626;
  transform: scale(1.05);
  box-shadow: 0 2px 6px rgba(220, 38, 38, 0.2);
}

.wf-fullscreen-content {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.wf-fullscreen-content :deep(.wf-compare-panel),
.wf-fullscreen-content :deep(.wf-list-panel) {
  height: 100%;
  max-height: none;
  border-top: none;
  border-radius: 0;
}

.wf-fullscreen-content :deep(.wf-compare-col) {
  height: 100%;
  max-height: none;
}

/* 过渡动画 */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

/* 深色模式 */
:root[data-theme="dark"] .wf-fullscreen-modal {
  background: rgba(0, 0, 0, 0.85);
}

:root[data-theme="dark"] .wf-fullscreen-container {
  background: #0e1422;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
}

:root[data-theme="dark"] .wf-fullscreen-header {
  background: linear-gradient(135deg, #0e1422 0%, #131b2c 100%);
  border-bottom-color: #1e2d45;
}

:root[data-theme="dark"] .wf-view-switcher {
  background: #0a0e1a;
  border-color: #1e2d45;
}

:root[data-theme="dark"] .wf-view-btn:hover {
  background: #131b2c;
}

:root[data-theme="dark"] .wf-view-btn.active {
  background: #131b2c;
}

:root[data-theme="dark"] .wf-close-btn {
  background: #131b2c;
  border-color: #1e2d45;
}

:root[data-theme="dark"] .wf-close-btn:hover {
  background: #7f1d1d;
  border-color: #dc2626;
}

:root[data-theme="dark"] .wf-fullscreen-count {
  background: #1e293b;
  color: #94a3b8;
  border-color: #334155;
}

/* 响应式 */
@media (max-width: 768px) {
  .wf-fullscreen-modal {
    padding: 0;
  }
  
  .wf-fullscreen-container {
    border-radius: 0;
    max-width: none;
  }
  
  .wf-fullscreen-header {
    padding: 16px 20px;
    flex-wrap: wrap;
    gap: 12px;
  }
  
  .wf-fullscreen-title {
    flex: 1 1 100%;
  }
  
  .wf-fullscreen-title h3 {
    font-size: 18px;
  }
  
  .wf-view-switcher {
    flex: 1;
  }
  
  .wf-view-btn span {
    display: none;
  }
}
</style>
