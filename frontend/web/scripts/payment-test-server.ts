// Explicit opt-in, loopback-only sandbox. PG calls are real TEST calls; orders are in memory.
// This adapter never grants application entitlements and is not included in production builds.
import { randomUUID } from 'node:crypto'
import type { PaymentOrder, PaymentState } from '../src/domain/payment.ts'

export const testProduct = { id: '66dd35ef-5c82-4cb0-85e9-320000000001', code: 'PREMIUM_TEST', name: '프리미엄 월 이용권 · 결제 연동 테스트', price: 14900, billingCycle: 'MONTHLY', childLimit: 1, active: true, features: {}, limits: {} }
type Row = { order: PaymentOrder; state: PaymentState; owner: string; createdAt: number; paymentKey?: string; inFlight?: Promise<Response> }
const reply = (data: unknown, status = 200) => Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } })
const problem = (code: string, status = 400) => reply({ code, title: '테스트 결제 요청을 확인해 주세요.', status }, status)

export function createPaymentSandbox(secret: string, fetcher: typeof fetch = fetch) {
  if (!/^test_gsk_/.test(secret)) throw new Error('Payment sandbox requires a test widget secret key')
  const rows = new Map<string, Row>(), creates = new Map<string, string>()
  const auth = 'Basic ' + Buffer.from(secret + ':').toString('base64')
  const visible = (row: Row) => row.state
  async function pg(row: Row, confirm = false) {
    try {
      const r = await fetcher('https://api.tosspayments.com' + (confirm ? '/v1/payments/confirm' : '/v1/payments/orders/' + encodeURIComponent(row.order.orderId)), {
        method: confirm ? 'POST' : 'GET', signal: AbortSignal.timeout(20000),
        headers: { Authorization: auth, 'Content-Type': 'application/json', ...(confirm ? { 'Idempotency-Key': row.order.orderId } : {}) },
        ...(confirm ? { body: JSON.stringify({ orderId: row.order.orderId, amount: row.order.amount, paymentKey: row.paymentKey }) } : {}),
      })
      const p = await r.json() as Record<string, unknown>
      if (r.ok && p.orderId === row.order.orderId && p.totalAmount === row.order.amount && p.currency === 'KRW'
          && typeof p.paymentKey === 'string' && (!row.paymentKey || row.paymentKey === p.paymentKey) && p.status === 'DONE') {
        row.state = { ...row.state, paymentId: row.order.orderId, status: 'APPROVED', entitlementStatus: 'SANDBOX_ONLY', approvedAt: typeof p.approvedAt === 'string' ? p.approvedAt : null }
        return reply(visible(row))
      }
      if (confirm && r.status >= 400 && r.status < 500 && ![408, 429].includes(r.status)) {
        row.state = { ...row.state, status: 'FAILED', failureCode: typeof p.code === 'string' && /^[A-Z_]+$/.test(p.code) ? p.code : 'PG_REJECTED' }
        return problem(row.state.failureCode!, 422)
      }
      return reply(visible(row), 202)
    } catch { return reply(visible(row), 202) }
  }
  return async (request: Request, owner: string) => {
    // Expired orders and their idempotency mappings are discarded together.
    for (const [id, row] of rows) if (Date.now() - row.createdAt > 3_600_000) rows.delete(id)
    for (const [key, id] of creates) if (!rows.has(id)) creates.delete(key)
    const path = new URL(request.url).pathname.replace('/__payment-test', '')
    if (request.method === 'GET' && path === '/products') return reply({ items: [testProduct] })
    if (request.method === 'POST') {
      if (request.headers.get('Origin') !== new URL(request.url).origin || request.headers.get('X-Requested-With') !== 'XMLHttpRequest') return problem('FORBIDDEN', 403)
      const idempotency = request.headers.get('Idempotency-Key') ?? ''
      if (!/^[0-9a-f-]{36}$/i.test(idempotency)) return problem('IDEMPOTENCY_KEY_REQUIRED')
      const b = await request.json() as Record<string, unknown>
      if (path === '/orders') {
        if (b.productId !== testProduct.id || typeof b.childId !== 'string' || !/^[\w-]{1,100}$/.test(b.childId)) return problem('INVALID_ORDER')
        const cacheKey = owner + ':' + idempotency, previous = creates.get(cacheKey)
        if (previous) {
          const row = rows.get(previous)!
          return row.order.childId === b.childId ? reply(row.order, 201) : problem('IDEMPOTENCY_CONFLICT', 409)
        }
        if (rows.size >= 100) return problem('SANDBOX_ORDER_LIMIT', 429)
        const order = { orderId: 'test-' + randomUUID(), amount: testProduct.price, orderName: testProduct.name, childId: b.childId, productId: testProduct.id }
        rows.set(order.orderId, { order, owner, createdAt: Date.now(), state: { orderId: order.orderId, childId: order.childId, amount: order.amount, paymentId: null, status: 'PENDING', entitlementStatus: null, approvedAt: null, failureCode: null } })
        creates.set(cacheKey, order.orderId)
        return reply(order, 201)
      }
      if (path === '/payments/confirm') {
        const row = typeof b.orderId === 'string' ? rows.get(b.orderId) : undefined
        if (!row || row.owner !== owner) return problem('ORDER_NOT_FOUND', 404)
        if (b.amount !== row.order.amount) return problem('PAYMENT_AMOUNT_MISMATCH', 422)
        if (typeof b.paymentKey !== 'string' || !b.paymentKey || b.paymentKey.length > 200) return problem('INVALID_PAYMENT_KEY')
        if (row.paymentKey && row.paymentKey !== b.paymentKey) return problem('PAYMENT_KEY_MISMATCH', 409)
        if (row.state.status === 'APPROVED') return reply(visible(row))
        if (row.inFlight) return (await row.inFlight).clone()
        row.paymentKey = b.paymentKey; row.state.status = 'CONFIRMING'
        row.inFlight = pg(row, true)
        try { return (await row.inFlight).clone() } finally { row.inFlight = undefined }
      }
    }
    if (request.method === 'GET' && path.startsWith('/payments/')) {
      const row = rows.get(decodeURIComponent(path.slice('/payments/'.length)))
      if (!row || row.owner !== owner) return problem('ORDER_NOT_FOUND', 404)
      if (row.inFlight) return reply(visible(row), 202)
      return row.state.status === 'CONFIRMING' ? pg(row) : reply(visible(row))
    }
    return problem('NOT_FOUND', 404)
  }
}
