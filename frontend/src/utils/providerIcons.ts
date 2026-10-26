/**
 * 供应商图标与品牌色。
 *
 * 品牌字形取自 cc-switch（MIT）的图标集，以 `?raw` 内联后由品牌色着色，
 * 避免 `currentColor` 失效导致「一块黑 logo」。
 * 没有品牌资源的供应商退回内置线性图标，保证每一项都有稳定标识。
 *
 * 新增品牌：把 SVG 放进 `src/assets/providers/`，再到 BRAND_GLYPHS 里加一行。
 */

import type { Component } from 'vue'
import {
  Boxes,
  Droplets,
  Monitor,
  Package,
  Plug,
  Server,
  Zap,
} from 'lucide-vue-next'

import copilotGlyph from '@/assets/providers/copilot.svg?raw'
import alibabaGlyph from '@/assets/providers/alibaba.svg?raw'
import anthropicGlyph from '@/assets/providers/anthropic.svg?raw'
import baiduGlyph from '@/assets/providers/baidu.svg?raw'
import bailianGlyph from '@/assets/providers/bailian.svg?raw'
import bytedanceGlyph from '@/assets/providers/bytedance.svg?raw'
import chatglmGlyph from '@/assets/providers/chatglm.svg?raw'
import claudeGlyph from '@/assets/providers/claude.svg?raw'
import cohereGlyph from '@/assets/providers/cohere.svg?raw'
import deepseekGlyph from '@/assets/providers/deepseek.svg?raw'
import doubaoGlyph from '@/assets/providers/doubao.svg?raw'
import geminiGlyph from '@/assets/providers/gemini.svg?raw'
import googleGlyph from '@/assets/providers/google.svg?raw'
import grokGlyph from '@/assets/providers/grok.svg?raw'
import huaweiGlyph from '@/assets/providers/huawei.svg?raw'
import huggingfaceGlyph from '@/assets/providers/huggingface.svg?raw'
import hunyuanGlyph from '@/assets/providers/hunyuan.svg?raw'
import kimiGlyph from '@/assets/providers/kimi.svg?raw'
import minimaxGlyph from '@/assets/providers/minimax.svg?raw'
import mistralGlyph from '@/assets/providers/mistral.svg?raw'
import modelscopeGlyph from '@/assets/providers/modelscope-color.svg?raw'
import newapiGlyph from '@/assets/providers/newapi.svg?raw'
import novitaGlyph from '@/assets/providers/novita.svg?raw'
import nvidiaGlyph from '@/assets/providers/nvidia.svg?raw'
import ollamaGlyph from '@/assets/providers/ollama.svg?raw'
import openaiGlyph from '@/assets/providers/openai.svg?raw'
import openrouterGlyph from '@/assets/providers/openrouter.svg?raw'
import perplexityGlyph from '@/assets/providers/perplexity.svg?raw'
import ppioGlyph from '@/assets/providers/ppio.svg?raw'
import qwenGlyph from '@/assets/providers/qwen.svg?raw'
import siliconflowGlyph from '@/assets/providers/siliconflow.svg?raw'
import stepfunGlyph from '@/assets/providers/stepfun.svg?raw'
import tencentGlyph from '@/assets/providers/tencent.svg?raw'
import wenxinGlyph from '@/assets/providers/wenxin.svg?raw'
import xaiGlyph from '@/assets/providers/xai.svg?raw'
import yiGlyph from '@/assets/providers/yi.svg?raw'
import zerooneGlyph from '@/assets/providers/zeroone.svg?raw'
import zhipuGlyph from '@/assets/providers/zhipu.svg?raw'

export interface ProviderVisual {
  /** 品牌字形（内联 SVG，随当前色着色） */
  glyph?: string
  /** 无品牌资源时的兜底图标 */
  icon?: Component
  /** 品牌主色：图标色 + 淡底色 */
  color: string
}

/** provider id（含常见别名）-> 品牌字形与主色 */
const BRAND_GLYPHS: Record<string, { glyph: string; color: string }> = {
  openrouter: { glyph: openrouterGlyph, color: '#8b5cf6' },
  anthropic: { glyph: anthropicGlyph, color: '#d97757' },
  claude: { glyph: claudeGlyph, color: '#d97757' },
  openai: { glyph: openaiGlyph, color: '#10a37f' },
  copilot: { glyph: copilotGlyph, color: '#24292f' },
  githubcopilot: { glyph: copilotGlyph, color: '#24292f' },
  deepseek: { glyph: deepseekGlyph, color: '#4d6bfe' },
  moonshot: { glyph: kimiGlyph, color: '#1f2937' },
  kimi: { glyph: kimiGlyph, color: '#1f2937' },
  zhipu: { glyph: zhipuGlyph, color: '#2563eb' },
  glm: { glyph: zhipuGlyph, color: '#2563eb' },
  chatglm: { glyph: chatglmGlyph, color: '#2563eb' },
  qwen: { glyph: qwenGlyph, color: '#ff6a00' },
  dashscope: { glyph: qwenGlyph, color: '#ff6a00' },
  qwencloud: { glyph: qwenGlyph, color: '#ff6a00' },
  alibaba: { glyph: alibabaGlyph, color: '#ff6a00' },
  bailian: { glyph: bailianGlyph, color: '#ff6a00' },
  hunyuan: { glyph: hunyuanGlyph, color: '#0052d9' },
  tencent: { glyph: tencentGlyph, color: '#0052d9' },
  ernie: { glyph: wenxinGlyph, color: '#2932e1' },
  wenxin: { glyph: wenxinGlyph, color: '#2932e1' },
  baidu: { glyph: baiduGlyph, color: '#2932e1' },
  doubao: { glyph: doubaoGlyph, color: '#1664ff' },
  volcengine: { glyph: doubaoGlyph, color: '#1664ff' },
  bytedance: { glyph: bytedanceGlyph, color: '#1664ff' },
  yi: { glyph: yiGlyph, color: '#0f766e' },
  zeroone: { glyph: zerooneGlyph, color: '#0f766e' },
  minimax: { glyph: minimaxGlyph, color: '#e8582a' },
  mistral: { glyph: mistralGlyph, color: '#ff7000' },
  cohere: { glyph: cohereGlyph, color: '#39594d' },
  ollama: { glyph: ollamaGlyph, color: '#334155' },
  gemini: { glyph: geminiGlyph, color: '#1a73e8' },
  google: { glyph: googleGlyph, color: '#1a73e8' },
  xai: { glyph: xaiGlyph, color: '#111827' },
  grok: { glyph: grokGlyph, color: '#111827' },
  siliconflow: { glyph: siliconflowGlyph, color: '#6d28d9' },
  novita: { glyph: novitaGlyph, color: '#2563eb' },
  ppio: { glyph: ppioGlyph, color: '#0ea5e9' },
  modelscope: { glyph: modelscopeGlyph, color: '#624aff' },
  stepfun: { glyph: stepfunGlyph, color: '#1d4ed8' },
  huawei: { glyph: huaweiGlyph, color: '#c7000b' },
  perplexity: { glyph: perplexityGlyph, color: '#20808d' },
  nvidia: { glyph: nvidiaGlyph, color: '#76b900' },
  huggingface: { glyph: huggingfaceGlyph, color: '#ffd21e' },
  newapi: { glyph: newapiGlyph, color: '#2563eb' },
}

/** 没有品牌资源的供应商用内置图标兜底 */
const FALLBACK_VISUALS: Record<string, { icon: Component; color: string }> = {
  groq: { icon: Zap, color: '#f55036' },
  together_ai: { icon: Boxes, color: '#0f766e' },
  baichuan: { icon: Droplets, color: '#0b7285' },
  vllm: { icon: Server, color: '#6d28d9' },
  lm_studio: { icon: Monitor, color: '#0ea5e9' },
  custom_openai: { icon: Plug, color: '#64748b' },
  custom_anthropic: { icon: Plug, color: '#64748b' },
}

const FALLBACK: ProviderVisual = { icon: Package, color: '#64748b' }

export function resolveProviderVisual(providerId: string | undefined): ProviderVisual {
  if (!providerId) {
    return FALLBACK
  }
  const brand = BRAND_GLYPHS[providerId]
  if (brand) {
    return { glyph: brand.glyph, color: brand.color }
  }
  return FALLBACK_VISUALS[providerId] || FALLBACK
}
