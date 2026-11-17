/**
 * 模型供应商设置的共享类型。
 *
 * 拆分后的模块边界：
 * - useProviderCatalog  供应商清单与选中态（导航、可添加项）
 * - useProviderDraft    连接草稿（名称/地址/协议/密钥）与测试
 * - useProviderModels   模型清单增删改排序
 * 三者共用这里的类型，避免各自重复声明。
 */

import type { ProviderApiType, ProviderModelEntry } from '@/api'

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
  /** 勾选中的思考档位（从低到高）；空数组=改用内置建议 */
  reasoningLevels: string[]
  /** 默认思考档位；空则取 reasoningLevels 首项 */
  reasoningLevel: string
}

/** 预设/编程套餐应用后的来源标记。 */
export interface AppliedSource {
  type: 'preset' | 'codingplan'
  label: string
}

/** 预设面板回填给本模块的配置。 */
export interface ApplyDraftPayload {
  provider: string
  model: string
  apiKey: string
  baseUrl?: string
  enabled: boolean
  temperature?: number
  maxTokens?: number
  maxIterations?: number
  source: 'preset' | 'codingplan'
  label: string
}

/** 左栏导航项。 */
export interface ProviderNavItem {
  id: string
  name: string
  /** 是否为全局当前使用模型所属供应商 */
  isCurrent: boolean
  /** 「N 个模型」/「没有可用模型」 */
  modelSummary: string
  statusClass: ProviderStatusClass
  /** 已保存的配置里有密钥或模型 */
  configured: boolean
  /** 本次刚通过添加入口接过、还没保存配好 */
  pendingSave: boolean
}

export type ProviderStatusClass = 'is-ready' | 'is-warning'

/** 连接测试结果。 */
export interface ConnectionTestResult {
  success: boolean
  message: string
}

/** 预设面板读取的当前草稿投影（与 ProviderPresetPanel 的入参一致）。 */
export interface ProviderDraftConfig {
  provider: string
  model: string
  apiKey: string
  baseUrl?: string
  enabled: boolean
  temperature?: number
  maxTokens?: number
  maxIterations?: number
}

/** 模型设置弹窗保存时提交给后端的载荷。 */
export interface ModelUpdatePayload {
  display_name: string | null
  clear_display_name: boolean
  context_window: number | null
  clear_context_window: boolean
  supports_image: boolean | null
  clear_supports_image: boolean
  /** 思考档位列表；空数组表示改用内置建议 */
  reasoning_levels: string[]
  /** 默认思考档位；空则清空 */
  reasoning_level: string | null
  clear_reasoning_level: boolean
}

export type ProviderModel = ProviderModelEntry
