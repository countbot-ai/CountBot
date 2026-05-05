/**
 * 头像管理 Composable
 * 
 * 提供用户和AI头像的自定义和持久化功能
 */

import { ref, computed } from 'vue'

const USER_AVATAR_KEY = 'CountBot-user-avatar'
const AI_AVATAR_KEY = 'CountBot-ai-avatar'

const userAvatarUrl = ref<string>('')
const aiAvatarUrl = ref<string>('')

export function useAvatar() {
    /**
     * 初始化头像（从localStorage加载）
     */
    function initAvatars() {
        const savedUserAvatar = localStorage.getItem(USER_AVATAR_KEY)
        const savedAiAvatar = localStorage.getItem(AI_AVATAR_KEY)

        if (savedUserAvatar) {
            userAvatarUrl.value = savedUserAvatar
        }
        if (savedAiAvatar) {
            aiAvatarUrl.value = savedAiAvatar
        }
    }

    /**
     * 设置用户头像
     */
    function setUserAvatar(url: string) {
        userAvatarUrl.value = url
        if (url) {
            localStorage.setItem(USER_AVATAR_KEY, url)
        } else {
            localStorage.removeItem(USER_AVATAR_KEY)
        }
    }

    /**
     * 设置AI头像
     */
    function setAiAvatar(url: string) {
        aiAvatarUrl.value = url
        if (url) {
            localStorage.setItem(AI_AVATAR_KEY, url)
        } else {
            localStorage.removeItem(AI_AVATAR_KEY)
        }
    }

    /**
     * 清除用户头像
     */
    function clearUserAvatar() {
        setUserAvatar('')
    }

    /**
     * 清除AI头像
     */
    function clearAiAvatar() {
        setAiAvatar('')
    }

    /**
     * 是否有自定义用户头像
     */
    const hasUserAvatar = computed(() => !!userAvatarUrl.value)

    /**
     * 是否有自定义AI头像
     */
    const hasAiAvatar = computed(() => !!aiAvatarUrl.value)

    return {
        // 状态
        userAvatarUrl,
        aiAvatarUrl,
        hasUserAvatar,
        hasAiAvatar,

        // 方法
        initAvatars,
        setUserAvatar,
        setAiAvatar,
        clearUserAvatar,
        clearAiAvatar
    }
}
