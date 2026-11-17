/** 当前登录用户与多角色状态；角色仅用于界面展示，鉴权以服务端为准 */

import { defineStore } from 'pinia'
import { authAPI, meAPI, type MeProfile } from '@/api/endpoints'

interface AuthStatus {
    is_local: boolean
    auth_enabled: boolean
    authenticated: boolean
    remote_access_enabled: boolean
    multiuser_enabled: boolean
    registration_open: boolean
    approval_mode: string
    role: string | null
}

interface UserState {
    status: AuthStatus | null
    profile: MeProfile | null
    loaded: boolean
    loading: boolean
}

/** 进行中的身份请求；用于合并并发加载 */
let profileRequest: Promise<MeProfile | null> | null = null

export const useUserStore = defineStore('user', {
    state: (): UserState => ({
        status: null,
        profile: null,
        loaded: false,
        loading: false,
    }),

    getters: {
        isAdmin: (state) => state.profile?.is_admin ?? state.status?.role === 'admin',
        isAuthenticated: (state) => state.status?.authenticated ?? false,
        registrationOpen: (state) => state.status?.registration_open ?? false,
        multiuserEnabled: (state) => state.status?.multiuser_enabled ?? false,
        displayName: (state) => state.profile?.display_name || state.profile?.username || '',
    },

    actions: {
        async loadStatus(force = false) {
            // 以 status 自身判断幂等；loaded 仅表示 profile 已加载
            if (this.status && !force) return this.status
            try {
                this.status = (await authAPI.status()) as unknown as AuthStatus
            } catch {
                this.status = null
            }
            return this.status
        },

        async loadProfile(force = false) {
            if (this.profile && !force) return this.profile
            // 并发调用共享同一请求，避免后来者拿到 null 且 loaded 恒为 false
            if (profileRequest) return profileRequest
            this.loading = true
            profileRequest = (async () => {
                try {
                    this.profile = await meAPI.profile()
                } catch {
                    this.profile = null
                } finally {
                    this.loading = false
                    this.loaded = true
                }
                return this.profile
            })()
            try {
                return await profileRequest
            } finally {
                profileRequest = null
            }
        },

        async refresh() {
            await this.loadStatus(true)
            await this.loadProfile(true)
        },

        reset() {
            this.status = null
            this.profile = null
            this.loaded = false
        },
    },
})
