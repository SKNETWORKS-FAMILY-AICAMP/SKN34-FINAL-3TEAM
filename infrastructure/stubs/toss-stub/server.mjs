// 토스페이먼츠 API 대역 (로컬·CI E2E 전용, #246). core TossClient가 호출하는 경로만 구현한다.
// 결제는 메모리에만 두고, 키는 test_ 접두사만 받는다.
import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

const mid = process.env.TOSS_TEST_MID
const billingMid = process.env.TOSS_TEST_BILLING_MID
const billingSecret = process.env.TOSS_TEST_BILLING_SECRET_KEY
if (!mid || !billingMid || !billingSecret) throw new Error('TOSS_TEST_MID·TOSS_TEST_BILLING_MID·TOSS_TEST_BILLING_SECRET_KEY 필요')

const byOrder = new Map(), byKey = new Map(), transactions = []
const json = (res, body, status = 200) => {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(body))
}
const notFound = (res) => json(res, { code: 'NOT_FOUND_PAYMENT', message: '결제 정보를 찾을 수 없습니다.' }, 404)
const approvedAt = () => new Date().toISOString().replace('Z', '+00:00')

function credential(req) {
  const [scheme, value] = (req.headers.authorization ?? '').split(' ')
  if (scheme !== 'Basic' || !value) return null
  const key = Buffer.from(value, 'base64').toString().replace(/:$/, '')
  return key.startsWith('test_') ? key : null
}

function approve(paymentKey, orderId, amount, merchant) {
  const payment = {
    paymentKey, orderId, status: 'DONE', mId: merchant, totalAmount: amount, balanceAmount: amount,
    approvedAt: approvedAt(), method: '카드', currency: 'KRW',
  }
  byOrder.set(orderId, payment); byKey.set(paymentKey, payment)
  transactions.push({ transactionKey: `e2e-tx-${randomUUID()}`, orderId, paymentKey, mId: merchant, amount, status: 'DONE' })
  return payment
}

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://toss-stub')
  if (req.method === 'GET' && url.pathname === '/health') return json(res, { status: 'UP' })
  const key = credential(req)
  if (!key) return json(res, { code: 'UNAUTHORIZED_KEY', message: '인증되지 않은 키입니다.' }, 401)
  const merchant = key === billingSecret ? billingMid : mid
  let raw = ''
  for await (const part of req) raw += part
  const body = raw ? JSON.parse(raw) : {}
  const path = url.pathname.split('/').map(decodeURIComponent)

  if (req.method === 'POST' && url.pathname === '/v1/payments/confirm') {
    if (!body.paymentKey || !body.orderId || !Number.isInteger(body.amount)) return json(res, { code: 'INVALID_REQUEST' }, 400)
    return json(res, byOrder.get(body.orderId) ?? approve(body.paymentKey, body.orderId, body.amount, merchant))
  }
  if (req.method === 'GET' && path[3] === 'orders' && path.length === 5) return byOrder.has(path[4]) ? json(res, byOrder.get(path[4])) : notFound(res)
  if (req.method === 'POST' && url.pathname === '/v1/billing/authorizations/issue')
    return json(res, { billingKey: `e2e-billing-${randomUUID()}`, customerKey: body.customerKey, mId: merchant })
  if (req.method === 'POST' && path[2] === 'billing' && path.length === 4)
    return json(res, byOrder.get(body.orderId) ?? approve(`e2e-pk-${randomUUID()}`, body.orderId, body.amount, merchant))
  if (req.method === 'POST' && path[2] === 'payments' && path[4] === 'cancel') {
    const payment = byKey.get(path[3])
    if (!payment) return notFound(res)
    Object.assign(payment, { status: 'CANCELED', balanceAmount: 0 })
    return json(res, payment)
  }
  if (req.method === 'GET' && url.pathname === '/v1/transactions')
    return json(res, transactions.filter((row) => row.mId === merchant))
  return json(res, { code: 'NOT_FOUND', message: '지원하지 않는 경로입니다.' }, 404)
}).listen(8080, '0.0.0.0')
