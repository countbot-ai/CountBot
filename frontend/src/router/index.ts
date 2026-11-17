/** Vue Router 配置：路由使用动态导入做代码分割 */

import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
    {
        path: '/',
        name: 'home',
        component: () => import('../modules/chat/NextChatWindow.vue'),
    },
    {
        // 旧版主窗口，保留用于对比与回退
        path: '/classic',
        name: 'classic-home',
        component: () => import('../modules/chat/ChatWindow.vue'),
    },
    {
        // 设置是独立页面：与主窗口同级，由路由承载当前分区（可直接分享/回退）
        path: '/settings/:tab?',
        name: 'settings',
        component: () => import(/* webpackChunkName: "settings" */ '../modules/settings/SettingsPage.vue'),
    },
    {
        path: '/login',
        name: 'login',
        component: () => import(/* webpackChunkName: "login" */ '../views/LoginView.vue'),
    },
    {
        path: '/setup/:setupSecret',
        name: 'setup',
        component: () => import(/* webpackChunkName: "login" */ '../views/LoginView.vue'),
    },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

export default router
