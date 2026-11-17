/** 把助手回答朗读出来（DeepSeek TTS）。 */

import { onBeforeUnmount, ref } from 'vue'
import { synthesizeSpeech } from '@/api'

export function useReadAloud() {
  const speaking = ref(false)
  let audio: HTMLAudioElement | null = null
  let objectUrl = ''

  function cleanup(): void {
    if (audio) {
      audio.pause()
      audio.src = ''
      audio = null
    }
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl)
      objectUrl = ''
    }
    speaking.value = false
  }

  async function speak(text: string, providerId: string, model: string): Promise<void> {
    const normalized = String(text || '').trim()
    if (!normalized || !providerId || !model) {
      return
    }
    cleanup()
    const blob = await synthesizeSpeech(normalized, providerId, model)
    objectUrl = URL.createObjectURL(blob)
    audio = new Audio(objectUrl)
    audio.onended = cleanup
    audio.onerror = cleanup
    speaking.value = true
    await audio.play()
  }

  function stop(): void {
    cleanup()
  }

  onBeforeUnmount(cleanup)

  return { speaking, speak, stop }
}
