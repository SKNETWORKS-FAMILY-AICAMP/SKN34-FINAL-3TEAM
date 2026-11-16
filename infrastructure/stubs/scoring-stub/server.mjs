// scoring-service 대역 (실서버 E2E 전용, #625). 실제 scoring은 S3 모델 아티팩트가 있어야 기동해 CI에서 쓸 수 없다.
// ai-service ScoringClient(app/clients/scoring_client.py)의 M2Scores 형식으로 고정 점수를 돌려준다.
// 점수는 정답 판정과 어긋나지 않도록 높게 둔다(서술 평균 >= M2_NARRATIVE_HIGH 4.0, ai cross_check.disagrees).
import { createServer } from 'node:http'

const json = (res, body, status = 200) => {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(body))
}

const NARRATIVE = { hol: 4, task_1: 5, content_1: 5, content_2: 5, content_3: 5, organization_1: 5, organization_2: 5, expression_1: 5, expression_2: 5 }
const ESSAY = { org: 3, cont: 3, exp: 3 }
const model = { name: 'e2e-stub', version: '1', revision: 1 }

function m2(body) {
  const scores = body.inputType === 'ESSAY' ? ESSAY : body.inputType === 'NARRATIVE' ? NARRATIVE : null
  if (!scores) return null
  return { active: true, inputType: body.inputType, scores, rawScores: { ...scores }, scored: true, model }
}

createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') return json(res, { status: 'UP' })
  if (req.method === 'POST' && (req.url === '/internal/m2/scores' || req.url === '/internal/m1/checks')) {
    let raw = ''
    for await (const part of req) raw += part
    let body
    try { body = JSON.parse(raw) } catch { return json(res, { title: 'invalid json' }, 400) }
    if (req.url === '/internal/m1/checks') return json(res, { active: false })
    const result = m2(body)
    return result ? json(res, result) : json(res, { title: 'unsupported inputType' }, 400)
  }
  return json(res, { title: 'not found' }, 404)
}).listen(8080, '0.0.0.0')
