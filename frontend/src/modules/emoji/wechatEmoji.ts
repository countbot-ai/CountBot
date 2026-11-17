/** 微信表情编码（如 [笑脸]）与 Unicode 表情的映射、解析与替换。 */

export interface WechatEmoji {
  /** 不含方括号的编码，例如「笑脸」 */
  code: string
  /** 展示用的 Unicode 表情 */
  char: string
}

/** 常用微信表情编码表；新增表情只需在这里补一行。 */
export const WECHAT_EMOJIS: readonly WechatEmoji[] = (
  [
    ['微笑', '😊'],
    // 「笑脸」是常见别名，和「微笑」指向同一表情
    ['笑脸', '😊'],
    ['撇嘴', '😒'],
    ['色', '😍'],
    ['发呆', '😳'],
    ['得意', '😎'],
    ['流泪', '😭'],
    ['害羞', '😊'],
    ['闭嘴', '🤐'],
    ['睡', '😴'],
    ['大哭', '😭'],
    ['尴尬', '😅'],
    ['发怒', '😠'],
    ['调皮', '😜'],
    ['呲牙', '😁'],
    ['惊讶', '😲'],
    ['难过', '😞'],
    ['酷', '😎'],
    ['冷汗', '😓'],
    ['抓狂', '😫'],
    ['吐', '🤮'],
    ['偷笑', '🤭'],
    ['愉快', '😄'],
    ['白眼', '🙄'],
    ['傲慢', '😤'],
    ['困', '😪'],
    ['惊恐', '😱'],
    ['流汗', '😅'],
    ['憨笑', '😄'],
    ['悠闲', '😌'],
    ['奋斗', '💪'],
    ['咒骂', '🤬'],
    ['疑问', '❓'],
    ['嘘', '🤫'],
    ['晕', '😵'],
    ['疯了', '🤪'],
    ['衰', '😩'],
    ['骷髅', '💀'],
    ['敲打', '🔨'],
    ['再见', '👋'],
    ['擦汗', '😅'],
    ['抠鼻', '🤏'],
    ['鼓掌', '👏'],
    ['糗大了', '😖'],
    ['坏笑', '😏'],
    ['左哼哼', '😤'],
    ['右哼哼', '😤'],
    ['哈欠', '😪'],
    ['鄙视', '😒'],
    ['委屈', '🥺'],
    ['快哭了', '🥹'],
    ['阴险', '😈'],
    ['亲亲', '😘'],
    ['吓', '😨'],
    ['可怜', '🥺'],
    ['菜刀', '🔪'],
    ['西瓜', '🍉'],
    ['啤酒', '🍺'],
    ['篮球', '🏀'],
    ['乒乓', '🏓'],
    ['咖啡', '☕'],
    ['饭', '🍚'],
    ['猪头', '🐷'],
    ['玫瑰', '🌹'],
    ['凋谢', '🥀'],
    ['示爱', '😘'],
    ['爱心', '❤️'],
    ['心碎', '💔'],
    ['蛋糕', '🎂'],
    ['闪电', '⚡'],
    ['炸弹', '💣'],
    ['刀', '🗡️'],
    ['足球', '⚽'],
    ['瓢虫', '🐞'],
    ['便便', '💩'],
    ['月亮', '🌙'],
    ['太阳', '☀️'],
    ['礼物', '🎁'],
    ['拥抱', '🤗'],
    ['强', '👍'],
    ['弱', '👎'],
    ['握手', '🤝'],
    ['胜利', '✌️'],
    ['抱拳', '🙏'],
    ['勾引', '😏'],
    ['拳头', '👊'],
    ['差劲', '👎'],
    ['爱你', '🤟'],
    ['NO', '❌'],
    ['OK', '👌'],
    ['爱情', '💑'],
    ['飞吻', '😘'],
    ['跳跳', '🕺'],
    ['发抖', '🥶'],
    ['怄火', '😡'],
    ['转圈', '🌀'],
    ['磕头', '🙇'],
    ['回头', '🔙'],
    ['跳绳', '🤸'],
    ['挥手', '👋'],
    ['激动', '🤩'],
    ['街舞', '🕺'],
    ['献吻', '😘'],
    ['左太极', '☯️'],
    ['右太极', '☯️'],
    ['嘿哈', '😆'],
    ['捂脸', '🤦'],
    ['破涕为笑', '😂'],
    ['奸笑', '😏'],
    ['机智', '🤓'],
    ['皱眉', '🙁'],
    ['耶', '✌️'],
    ['红包', '🧧'],
    ['發', '🀄'],
    ['庆祝', '🎉'],
    ['吃瓜', '🍉'],
    ['加油', '💪'],
    ['汗', '😅'],
    ['天啊', '😱'],
    ['社会社会', '😎'],
    ['旺柴', '🐶'],
    ['打脸', '🤕'],
    ['哇', '🤩'],
    ['翻白眼', '🙄'],
    ['666', '👏'],
    ['让我看看', '👀'],
    ['叹气', '😮‍💨'],
    ['苦涩', '😣'],
    ['裂开', '💔'],
    ['Emm', '😑'],
    ['好的', '👌'],
  ] as const
).map(([code, char]) => ({ code, char }))

const EMOJI_BY_CODE = new Map(WECHAT_EMOJIS.map(emoji => [emoji.code, emoji]))

/** 微信表情编码的形状：方括号内 1~10 个非方括号字符。 */
const EMOJI_CODE_PATTERN = /\[([^\[\]\n]{1,10})\]/g

export interface WechatEmojiSegment {
  type: 'text' | 'emoji'
  value: string
  /** 表情片段对应的编码，纯文本片段为空 */
  code?: string
}

function createCodePattern(): RegExp {
  return new RegExp(EMOJI_CODE_PATTERN.source, 'g')
}

/** 是否为已收录的微信表情编码（可带方括号）。 */
export function isWechatEmojiCode(code: string): boolean {
  return EMOJI_BY_CODE.has(code.replace(/^\[|\]$/g, ''))
}

function renderEmojiHtml(emoji: WechatEmoji): string {
  return `<span class="wx-emoji" role="img" aria-label="${emoji.code}" title="${emoji.code}">${emoji.char}</span>`
}

/** 纯文本替换：把 `[笑脸]` 变成对应表情字符，未收录的编码原样保留。 */
export function replaceWechatEmojiCodes(text: string): string {
  if (!text || !text.includes('[')) {
    return text
  }

  return text.replace(createCodePattern(), (raw, code: string) => {
    const emoji = EMOJI_BY_CODE.get(code)
    return emoji ? emoji.char : raw
  })
}

/** 把纯文本切成文本/表情片段，交给模板逐段渲染（不生成 HTML）。 */
export function parseWechatEmojiText(text: string): WechatEmojiSegment[] {
  const source = text || ''
  if (!source.includes('[')) {
    return [{ type: 'text', value: source }]
  }

  const segments: WechatEmojiSegment[] = []
  const pattern = createCodePattern()
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(source)) !== null) {
    const emoji = EMOJI_BY_CODE.get(match[1])
    if (!emoji) {
      // 未收录的编码留在文本里，继续向后找下一个已知表情
      continue
    }

    if (match.index > lastIndex) {
      segments.push({ type: 'text', value: source.slice(lastIndex, match.index) })
    }
    segments.push({ type: 'emoji', value: emoji.char, code: emoji.code })
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < source.length) {
    segments.push({ type: 'text', value: source.slice(lastIndex) })
  }

  return segments.length > 0 ? segments : [{ type: 'text', value: source }]
}

/** Markdown 渲染后需要跳过的标签：代码、脚本与样式不参与表情替换。 */
const SKIP_OPEN_TAG = /^<(code|pre|script|style)\b/i
const SKIP_CLOSE_TAG = /^<\/(code|pre|script|style)\s*>/i

/** 只替换 HTML 文本节点中的表情编码，跳过代码与脚本区域。 */
export function replaceWechatEmojisInHtml(html: string): string {
  if (!html || !html.includes('[')) {
    return html
  }

  let skipDepth = 0
  let result = ''

  // split 后奇数位是标签，偶数位是文本节点
  for (const token of html.split(/(<[^>]*>)/g)) {
    if (!token) {
      continue
    }

    if (token.startsWith('<')) {
      if (SKIP_OPEN_TAG.test(token)) {
        skipDepth += 1
      } else if (SKIP_CLOSE_TAG.test(token)) {
        skipDepth = Math.max(0, skipDepth - 1)
      }
      result += token
      continue
    }

    result += skipDepth > 0
      ? token
      : token.replace(createCodePattern(), (raw, code: string) => {
          const emoji = EMOJI_BY_CODE.get(code)
          return emoji ? renderEmojiHtml(emoji) : raw
        })
  }

  return result
}
