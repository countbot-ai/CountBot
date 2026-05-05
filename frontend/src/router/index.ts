/**
 * Vue Router 配置
 * 使用动态导入实现代码分割，提升首屏加载速度
 */

import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
    {
        path: '/',
        name: 'home',
        component: () => import('../modules/chat/ChatWindow.vue'),
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
