/** 微信表情模块对外入口。 */
export {
  WECHAT_EMOJIS,
  isWechatEmojiCode,
  parseWechatEmojiText,
  replaceWechatEmojiCodes,
  replaceWechatEmojisInHtml,
} from './wechatEmoji'
export type { WechatEmoji, WechatEmojiSegment } from './wechatEmoji'
export { default as EmojiText } from './EmojiText.vue'
