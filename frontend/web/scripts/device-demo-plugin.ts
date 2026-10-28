import type { Plugin } from 'vite'
import { networkInterfaces } from 'node:os'
import { createDeviceDemo } from './device-demo.ts'

export function deviceDemoPlugin(enabled: boolean): Plugin {
  return {
    name: 'shared-device-demo', apply: 'serve',
    configureServer(server) {
      if (!enabled) return
      const demo = createDeviceDemo()
      server.middlewares.use('/__demo/device', async (req, res) => {
        try {
          const protocol = server.config.server.https ? 'https:' : 'http:'
          const origin = `${protocol}//${req.headers.host}`
          const chunks: Buffer[] = []
          let size = 0
          for await (const chunk of req) {
            size += chunk.length
            if (size > 32_768) { res.writeHead(413).end(); return }
            chunks.push(Buffer.from(chunk))
          }
          const headers = new Headers()
          for (const [key, value] of Object.entries(req.headers))
            if (value) headers.set(key, Array.isArray(value) ? value.join(', ') : value)
          const request = new Request(origin + '/__demo/device' + req.url, {
            method: req.method, headers, ...(chunks.length ? { body: Buffer.concat(chunks).toString() } : {}),
          })
          let response = await demo.handle(request)
          if (new URL(request.url).pathname === '/__demo/device/instance' && response.ok) {
            const address = server.httpServer?.address()
            const port = address && typeof address === 'object' ? address.port : server.config.server.port
            const origins = Object.entries(networkInterfaces()).flatMap(([name, entries]) =>
              (entries ?? []).filter((a) => a.family === 'IPv4' && !a.internal)
                .map((a) => ({ label: name, origin: `${protocol}//${a.address}:${port}` })))
            response = Response.json({ instanceId: demo.instanceId, origins }, { headers: { 'Cache-Control': 'no-store' } })
          }
          response.headers.forEach((value, key) => res.setHeader(key, value))
          res.writeHead(response.status).end(await response.text())
        } catch {
          res.writeHead(503, { 'Content-Type': 'application/problem+json', 'Cache-Control': 'no-store' })
            .end(JSON.stringify({ code: 'DEMO_UNAVAILABLE', title: '공유 시연 서버에 연결하지 못했습니다.' }))
        }
      })
    },
  }
}
