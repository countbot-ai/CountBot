/** 原生能力独立接口：语音识别与语音合成。 */

import apiClient from './client'

export interface SpeechTranscription {
  text: string
  duration_ms: number
  request_id: string
}

export interface SpeechStatus {
  provider_id: string
  model: string
  asr_enabled: boolean
  tts_enabled: boolean
  has_api_key: boolean
  ready: boolean
  tts_ready: boolean
  reason: string
  message: string
}

export async function getSpeechStatus(
  providerId: string,
  model: string,
): Promise<SpeechStatus> {
  return apiClient.get('/native-caps/speech/status', {
    params: { provider_id: providerId, model },
  })
}

export async function transcribeAudio(
  file: File | Blob,
  providerId: string,
  model: string,
): Promise<SpeechTranscription> {
  const form = new FormData()
  form.append('file', file, file instanceof File ? file.name : 'recording.webm')
  form.append('provider_id', providerId)
  form.append('model', model)
  return apiClient.post('/native-caps/speech/asr', form, {
    timeout: 60000,
  })
}

export async function synthesizeSpeech(
  text: string,
  providerId: string,
  model: string,
  voiceId = 'stella',
  format: 'wav' | 'pcm' = 'wav',
): Promise<Blob> {
  const response = await apiClient.post(
    '/native-caps/speech/tts',
    { provider_id: providerId, model, text, voice_id: voiceId, format },
    { responseType: 'blob', timeout: 180000 },
  )
  return response as unknown as Blob
}
