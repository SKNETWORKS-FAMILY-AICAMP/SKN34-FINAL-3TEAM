import { API_BASE, toApiError, withAuth } from './apiClient.ts'

/** SSE 이벤트 (API 명세서 1.6: status·clarification·delta·result·error·done) */
export interface SseEvent {
  event: string
  data: unknown
}

interface StreamOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
  onEvent: (event: SseEvent) => void
}

/** 인증 헤더가 필요해 EventSource 대신 fetch 스트림으로 수신 */
export async function streamSse(path: string, { method = 'POST', body, signal, onEvent }: StreamOptions) {
  const headers = withAuth({ Accept: 'text/event-stream' })
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  const response = await fetch(API_BASE + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
    credentials: 'same-origin',
  })
  if (!response.ok || !response.body) throw await toApiError(response)

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer = (buffer + value).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const parsed = parseBlock(buffer.slice(0, boundary))
      if (parsed) onEvent(parsed)
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
    }
  }
}

function parseBlock(block: string): SseEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue // heartbeat `: ping`
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  return data.length === 0 ? null : { event, data: JSON.parse(data.join('\n')) }
}
