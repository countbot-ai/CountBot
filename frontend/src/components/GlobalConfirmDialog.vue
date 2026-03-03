<template>
  <ConfirmDialog
    :show="confirmState.show"
    :title="confirmState.title"
    :message="confirmState.message"
    :icon="confirmState.icon"
    :type="confirmState.type"
    :confirm-text="confirmState.confirmText"
    :cancel-text="confirmState.cancelText"
    :confirm-variant="confirmState.confirmVariant"
    :loading="confirmState.loading"
    @confirm="handleConfirm"
    @cancel="handleCancel"
  />
</template>

<script setup lang="ts">
import ConfirmDialog from './ui/ConfirmDialog.vue'
import { useConfirm } from '@/composables/useConfirm'

const { state: confirmState, handleConfirm, handleCancel } = useConfirm()
</script>
