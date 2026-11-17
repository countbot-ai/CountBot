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
import { useUserStore } from '@/store/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const { initTheme } = useTheme()

// 安全警告标志：远程访问已开启但未设置密码
const showSecurityWarning = ref(false)
provide('showSecurityWarning', showSecurityWarning)

onMounted(async () => {
  initTheme()

  // 登录态统一存到 store，避免各处请求读到 status=null 而误判角色
  const authStatus = await userStore.loadStatus().catch(() => null)

  if (route.path !== '/') {
    return
  }
  if (!authStatus) {
    // auth 接口不可用时不阻塞（可能是旧版本后端）
    return
  }

  // 多用户模式下本机也不再免登录（后端已关闭回环旁路）；桌面单用户 + 本机才放行
  const needsLogin =
    !authStatus.authenticated &&
    (authStatus.multiuser_enabled || !authStatus.is_local)

  if (needsLogin) {
    // 未认证且不允许本机旁路 → 跳转登录
    router.replace('/login')
  } else if (authStatus.remote_access_enabled && !authStatus.auth_enabled) {
    // 远程访问已开启但未设置密码 → 显示安全警告（不阻塞）
    showSecurityWarning.value = true
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
