// OpenAI 호환 LLM 대역 (로컬·CI E2E·부하 시험 전용, #246·#361). ai-service의 chat.completions 호출만 받는다.
// 응답은 response_format.json_schema.name(ai-service Pydantic 모델 이름)으로 고른다.
// LLM_STUB_DELAY_MS(기본 0)·LLM_STUB_JITTER_MS(기본 0): 응답 전 대기(기본값 + 0~지터 균등). 부하 시험에서 실제 LLM 지연을 흉내 낸다.
import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

const delayMs = Math.max(0, Number(process.env.LLM_STUB_DELAY_MS ?? 0) || 0)
const jitterMs = Math.max(0, Number(process.env.LLM_STUB_JITTER_MS ?? 0) || 0)
const wait = () => {
  const ms = delayMs + Math.random() * jitterMs
  return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve()
}

const json = (res, body, status = 200) => {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(body))
}

// judgment/prompts.py build_user 형식: "- elementId: X" 목록과 <answer>…</answer> 본문
function extraction(user) {
  const answer = user.match(/<answer>\n([\s\S]*)\n<\/answer>/)?.[1] ?? ''
  const ids = [...user.matchAll(/^- elementId: (\S+)$/gm)].map((match) => match[1])
  return { elements: ids.map((elementId) => ({ elementId, status: 'FOUND', quote: answer })) }
}

const fixed = {
  GeneratedQuestion: () => ({ question: '그렇게 생각한 까닭을 한 가지 더 이야기해 줄래요?' }),
  // 숫자를 넣지 않아 서술 수치 검증과 충돌하지 않는다.
  GeneratedNarrative: () => ({
    narrative: '이번 주 기록을 바탕으로 만든 시험용 요약입니다.',
    evening_question: '오늘 가장 재미있었던 생각은 무엇이었니?',
    cited_quotes: [],
  }),
  Classification: () => ({ intent: 'COUNT', scopeIssue: 'NONE' }),
  TemplateProposal: () => ({ clarification: '어떤 순서로 보여 드릴까요?' }),
}

function completion(body) {
  const name = body.response_format?.json_schema?.name
  const user = body.messages?.find((message) => message.role === 'user')?.content ?? ''
  const output = name === 'Extraction' ? extraction(user) : fixed[name]?.()
  if (!output) return null
  return {
    id: `chatcmpl-${randomUUID()}`, object: 'chat.completion', created: Math.floor(Date.now() / 1000), model: body.model,
    choices: [{ index: 0, message: { role: 'assistant', content: JSON.stringify(output), refusal: null }, finish_reason: 'stop' }],
    usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
  }
}

function stream(res, model) {
  const id = `chatcmpl-${randomUUID()}`, created = Math.floor(Date.now() / 1000)
  const chunk = (choices, usage = null) => `data: ${JSON.stringify({ id, object: 'chat.completion.chunk', created, model, choices, usage })}\n\n`
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' })
  res.write(chunk([{ index: 0, delta: { role: 'assistant', content: '시험용 대역 답변입니다.' }, finish_reason: null }]))
  res.write(chunk([{ index: 0, delta: {}, finish_reason: 'stop' }]))
  res.write(chunk([], { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 }))
  res.end('data: [DONE]\n\n')
}

createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') return json(res, { status: 'UP' })
  if (req.method === 'POST' && req.url === '/v1/chat/completions') {
    let raw = ''
    for await (const part of req) raw += part
    let body
    try { body = JSON.parse(raw) } catch { return json(res, { error: { message: 'invalid json' } }, 400) }
    await wait()
    if (body.stream) return stream(res, body.model)
    const result = completion(body)
    return result ? json(res, result) : json(res, { error: { message: 'unsupported response_format' } }, 400)
  }
  return json(res, { error: { message: 'not found' } }, 404)
}).listen(8080, '0.0.0.0')
