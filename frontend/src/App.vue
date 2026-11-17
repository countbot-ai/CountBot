<template>
  <div id="app">
    <router-view />
    <Toast />
    <GlobalConfirmDialog />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Toast from '@/components/ui/Toast.vue'
import GlobalConfirmDialog from '@/components/GlobalConfirmDialog.vue'
import { useTheme } from '@/composables/useTheme'
import { authAPI } from '@/api'

const router = useRouter()
const route = useRoute()
const { initTheme } = useTheme()

// 安全警告标志：远程访问已开启但未设置密码
const showSecurityWarning = ref(false)
provide('showSecurityWarning', showSecurityWarning)

onMounted(async () => {
  initTheme()
  if (route.path !== '/') {
    return
  }

  // 远程访问认证检查
  try {
    const data = await authAPI.status()
    if (!data.is_local && !data.authenticated) {
      // 远程访问且未认证 → 跳转登录
      router.replace('/login')
    } else if (data.remote_access_enabled && !data.auth_enabled) {
      // 远程访问已开启但未设置密码 → 显示安全警告（不阻塞）
      showSecurityWarning.value = true
    }
  } catch {
    // auth 接口不可用时不阻塞（可能是旧版本后端）
  }
})
</script>

<style>
#app {
  width: 100%;
  height: 100vh;
  overflow: hidden;
}
</style>
