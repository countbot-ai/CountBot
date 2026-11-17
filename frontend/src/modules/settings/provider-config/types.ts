/** 模型供应商设置的共享类型，供 provider 相关 composable 复用 */

import type { ProviderApiType, ProviderModelEntry } from '@/api'
import type { NativeCapabilities } from '@/types/nativeCaps'

/** 连接草稿：与后端 provider 配置一一对应（不含 models）。 */
export interface ProviderDraft {
  apiKey: string
  apiKeys: string[]
  baseUrl: string
  enabled: boolean
  name: string
  apiType: ProviderApiType
}

/** 模型设置弹窗里的编辑草稿。 */
export interface ModelEditorDraft {
  displayName: string
  contextWindow: string
  supportsImage: 'auto' | 'on' | 'off'
  /** 输出模式：inherit=跟随全局，stream=强制流式，non-stream=强制非流式 */
  streamMode: 'inherit' | 'stream' | 'non-stream'
  /** 勾选中的思考档位（从低到高）；空数组=改用内置建议 */
  reasoningLevels: string[]
  /** 默认思考档位；空则取 reasoningLevels 首项 */
  reasoningLevel: string
  /** 是否共享给普通用户 */
  shared: boolean
  /** 用户可见别名；空则回落到 display_name 或 id */
  sharedAlias: string
  /** 共享说明 */
  sharedNote: string
  /** 每用户每日调用上限（字符串便于输入框双向绑定）；空=不限 */
  userDailyLimit: string
  /** 供应商原生能力开关 */
  nativeCapabilities: NativeCapabilities
}

/** 左栏导航项。 */
export interface ProviderNavItem {
  id: string
  name: string
  /** 是否为全局当前使用模型所属供应商 */
  isCurrent: boolean
  /** 「N 个模型」/「没有可用模型」 */
  modelSummary: string
  /** 可用状态的短文案（可用 / 缺少 API Key / 未启用） */
  statusText: string
  statusClass: ProviderStatusClass
  /** 已保存的配置里有密钥或模型 */
  configured: boolean
  /** 本次刚通过添加入口接过、还没保存配好 */
  pendingSave: boolean
  /** 草稿与已保存配置不一致（未落库的连接信息） */
  dirty: boolean
}

export type ProviderStatusClass = 'is-ready' | 'is-warning'

/** 供应商级连通性测试结果（只拉模型列表，不消耗对话 token）。 */
export interface ProviderTestResult {
  success: boolean
  latencyMs: number | null
  modelCount: number | null
  error: string
}

/** 连接测试结果。 */
export interface ConnectionTestResult {
  success: boolean
  message: string
}

/** 模型设置弹窗保存时提交给后端的载荷。 */
export interface ModelUpdatePayload {
  display_name: string | null
  clear_display_name: boolean
  context_window: number | null
  clear_context_window: boolean
  supports_image: boolean | null
  clear_supports_image: boolean
  /** 输出模式：null 表示跟随全局 */
  stream_enabled: boolean | null
  clear_stream_enabled: boolean
  /** 思考档位列表；空数组表示改用内置建议 */
  reasoning_levels: string[]
  /** 默认思考档位；空则清空 */
  reasoning_level: string | null
  clear_reasoning_level: boolean
  /** 共享给普通用户；关闭后别名与限额一并清空 */
  shared: boolean
  shared_alias: string | null
  clear_shared_alias: boolean
  shared_note: string | null
  clear_shared_note: boolean
  user_daily_limit: number | null
  clear_user_daily_limit: boolean
  /** 原生能力开关；整体覆盖写入 */
  native_capabilities: NativeCapabilities
}

export type ProviderModel = ProviderModelEntry
