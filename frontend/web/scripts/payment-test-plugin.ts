import type { Plugin } from 'vite'
import { randomUUID } from 'node:crypto'
import { createPaymentSandbox } from './payment-test-server.ts'

export function paymentTestPlugin(enabled: boolean, secret: string): Plugin {
  return { name: 'toss-payment-test', apply: 'serve', configureServer(server) {
    if (!enabled) return
    const handle = createPaymentSandbox(secret)
    const sessions = new Set<string>()
    server.middlewares.use('/__payment-test', async (req, res) => {
      const noStore = { 'Content-Type': 'application/problem+json', 'Cache-Control': 'no-store' }
      try {
        // Do not expose a payment proxy to a LAN or a reverse-proxied public site.
        if (!['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress ?? '') || !/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(req.headers.host ?? '')) {
          res.writeHead(403, noStore).end(JSON.stringify({ code: 'LOOPBACK_ONLY', title: '로컬 테스트 전용입니다.' })); return
        }
        let owner = /(?:^|;\s*)sagomungchi-payment-test=([0-9a-f-]{36})(?:;|$)/i.exec(req.headers.cookie ?? '')?.[1]
        if (!owner || !sessions.has(owner)) {
          if (sessions.size >= 100) { res.writeHead(429, noStore).end(); return }
          owner = randomUUID(); sessions.add(owner)
          res.setHeader('Set-Cookie', `sagomungchi-payment-test=${owner}; HttpOnly; SameSite=Lax; Path=/__payment-test; Max-Age=3600`)
        }
        const chunks: Buffer[] = []; let size = 0
        for await (const chunk of req) { size += chunk.length; if (size > 8192) { res.writeHead(413, noStore).end(); return }; chunks.push(Buffer.from(chunk)) }
        const headers = new Headers()
        for (const [key, value] of Object.entries(req.headers)) if (value) headers.set(key, Array.isArray(value) ? value.join(', ') : value)
        const request = new Request(`http://${req.headers.host}/__payment-test${req.url}`, { method: req.method, headers, ...(chunks.length ? { body: Buffer.concat(chunks) } : {}) })
        const response = await handle(request, owner)
        response.headers.forEach((v, k) => res.setHeader(k, v))
        res.writeHead(response.status).end(await response.text())
      } catch { res.writeHead(503, noStore).end(JSON.stringify({ code: 'PAYMENT_TEST_UNAVAILABLE', title: '테스트 결제 서버를 확인해 주세요.' })) }
    })
  } }
}
