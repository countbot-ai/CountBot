/**
 * Coding Plan 预设配置
 * 国内AI厂商提供的编程优惠计划
 */

export interface CodingPlanPreset {
  id: string
  vendor: string // 厂商名称（国际化 key）
  models: string[] // 支持的模型列表
  openaiBaseUrl: string // OpenAI兼容Base URL
  anthropicBaseUrl?: string // Anthropic兼容Base URL (可选)
  subscribeUrl: string // 订阅链接
  sourceUrl: string // 来源文档
  defaultModel: string // 默认模型
}

export const CODING_PLAN_PRESETS: CodingPlanPreset[] = [
  {
    id: 'aliyun',
    vendor: 'aliyun', // 使用 i18n key
    models: [
      'qwen3.5-plus',
      'qwen3-max-2026-01-23',
      'qwen3-coder-next',
      'qwen3-coder-plus',
      'glm-5',
      'glm-4.7',
      'kimi-k2.5',
      'MiniMax-M2.5'
    ],
    openaiBaseUrl: 'https://coding.dashscope.aliyuncs.com/v1',
    anthropicBaseUrl: 'https://coding.dashscope.aliyuncs.com/apps/anthropic',
    subscribeUrl: 'https://bailian.console.aliyun.com/#/coding-plan',
    sourceUrl: 'https://help.aliyun.com/zh/model-studio/user-guide/coding-plan',
    defaultModel: 'qwen3.5-plus'
  },
  {
    id: 'volcengine',
    vendor: 'volcengine',
    models: [
      'doubao-seed-2.0-code',
      'doubao-seed-2.0-prod',
      'doubao-seed-2.0-lite',
      'doubao-seed-code',
      'minimax-m2.5',
      'glm-4.7',
      'deepseek-v3.2',
      'kimi-k2.5'
    ],
    openaiBaseUrl: 'https://ark.cn-beijing.volces.com/api/coding/v3',
    anthropicBaseUrl: 'https://ark.cn-beijing.volces.com/api/coding',
    subscribeUrl: 'https://volcengine.com/L/zZdizOaGY_g/',
    sourceUrl: 'https://volcengine.com/L/zZdizOaGY_g/',
    defaultModel: 'doubao-seed-2.0-code'
  },
  {
    id: 'zhipu',
    vendor: 'zhipu',
    models: ['GLM-5', 'GLM-4.7', 'GLM-4.6'],
    openaiBaseUrl: 'https://open.bigmodel.cn/api/coding/paas/v4',
    anthropicBaseUrl: 'https://open.bigmodel.cn/api/coding/anthropic',
    subscribeUrl: 'https://www.bigmodel.cn/glm-coding?ic=WOXDRLIM0U',
    sourceUrl: 'https://www.bigmodel.cn/glm-coding?ic=WOXDRLIM0U',
    defaultModel: 'GLM-5'
  },
  {
    id: 'minimax',
    vendor: 'minimax',
    models: ['MiniMax-M2.5', 'M2.5-Highspeed', 'M2.1', 'M2'],
    openaiBaseUrl: 'https://api.minimaxi.com/coding/v1',
    anthropicBaseUrl: 'https://api.minimaxi.com/anthropic/coding',
    subscribeUrl: 'https://www.minimaxi.com/subscribe/coding-plan',
    sourceUrl: 'https://platform.minimaxi.com/document/guides/chat-model/V2',
    defaultModel: 'MiniMax-M2.5'
  },
  {
    id: 'moonshot',
    vendor: 'moonshot',
    models: ['Kimi-K2.5', 'K2-Thinking'],
    openaiBaseUrl: 'https://api.moonshot.cn/coding/v1',
    subscribeUrl: 'https://www.kimi.com/code/docs/',
    sourceUrl: 'https://www.kimi.com/code/docs/',
    defaultModel: 'Kimi-K2.5'
  },
  {
    id: 'mthreads',
    vendor: 'mthreads',
    models: ['GLM-4.7'],
    openaiBaseUrl: 'https://code-api.mthreads.com/v1',
    subscribeUrl: 'https://code.mthreads.com/',
    sourceUrl: 'https://code.mthreads.com/',
    defaultModel: 'GLM-4.7'
  },
  {
    id: 'baidu',
    vendor: 'baidu',
    models: ['GLM-5', 'Kimi-K2.5', 'MiniMax-M2.1', 'DeepSeek-V3.2'],
    openaiBaseUrl: 'https://qianfan.baidubce.com/v2/coding',
    subscribeUrl: 'https://cloud.baidu.com/product/codingplan.html',
    sourceUrl: 'https://cloud.baidu.com/doc/WENXINWORKSHOP/s/jlil56u11',
    defaultModel: 'GLM-5'
  },
  {
    id: 'infini',
    vendor: 'infini',
    models: [
      'deepseek-v3.2',
      'deepseek-v3.2-thinking',
      'kimi-2.5',
      'minimax-m2.1',
      'minimax-m2.5',
      'glm-4.7',
      'glm-5'
    ],
    openaiBaseUrl: 'https://cloud.infini-ai.com/maas/coding/v1',
    anthropicBaseUrl: 'https://cloud.infini-ai.com/maas/coding/v1/messages',
    subscribeUrl: 'https://cloud.infini-ai.com/platform/ai',
    sourceUrl: 'https://docs.infini-ai.com/gen-studio/coding-plan/',
    defaultModel: 'deepseek-v3.2'
  },
  {
    id: 'kuaishou',
    vendor: 'kuaishou',
    models: ['KAT-Coder-Pro-V1'],
    openaiBaseUrl: 'https://kat-api.kuaishou.com/v1',
    subscribeUrl: 'https://www.streamlake.com/marketing/coding-plan',
    sourceUrl: 'https://www.streamlake.com/marketing/coding-plan',
    defaultModel: 'KAT-Coder-Pro-V1'
  },
  {
    id: 'deepseek',
    vendor: 'deepseek',
    models: ['DeepSeek-V3', 'DeepSeek-R1'],
    openaiBaseUrl: 'https://api.deepseek.com/v1',
    subscribeUrl: 'https://platform.deepseek.com',
    sourceUrl: 'https://api-docs.deepseek.com/zh-cn/',
    defaultModel: 'DeepSeek-V3'
  }
]
