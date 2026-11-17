/**
 * 设计预览入口（仅开发态使用）
 *
 * 独立于 src/main.ts 的第二个 Vite 入口，不参与生产构建（rollup 只打包 index.html）。
 * 用途：在没有后端的情况下渲染真实组件（ChatHeader / MessageList / ChatInput），
 * 用 mock 数据校验消息流、思考块、工具调用、多智能体面板的实际视觉。
 */
import { createApp } from 'vue'
import { pinia } from '../src/store'
import i18n from '../src/i18n'
import '../src/assets/styles/main.css'
import PreviewApp from './PreviewApp.vue'

// 无后端环境的数据桩：wiki / cron 列表返回空，面板就能渲染出真实的空态样式
const realFetch = window.fetch.bind(window)
window.fetch = (input, init) => {
  const url = typeof input === 'string' ? input : (input as Request).url
  if (url.includes('/api/wiki')) {
    return Promise.resolve(new Response(JSON.stringify({ entries: [], stats: null }), {
      headers: { 'Content-Type': 'application/json' },
    }))
  }
  if (url.includes('/api/cron')) {
    return Promise.resolve(new Response(JSON.stringify({ jobs: [] }), {
      headers: { 'Content-Type': 'application/json' },
    }))
  }
  return realFetch(input as RequestInfo, init)
}

createApp(PreviewApp).use(pinia).use(i18n).mount('#app')
