// npm run dev:qr -- --port 5196 (별도 프로세스·추가 패키지 없이 Vite 안에서 실행)
process.env.VITE_API_MOCK = 'true'
process.env.VITE_SHARED_DEVICE_MOCK = 'true'
const { createServer } = await import('vite')
const index = process.argv.indexOf('--port')
const port = index < 0 ? 5196 : Number(process.argv[index + 1])
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('--port 값을 확인해 주세요.')
const server = await createServer({ mode: 'qr-demo', server: { host: '0.0.0.0', port, strictPort: true } })
await server.listen()
console.log('\n사고뭉치 QR 시연 전용: 같은 Wi-Fi에서 접속하고 가상 정보만 사용하세요.\n')
server.printUrls()
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { void server.close().then(() => process.exit()) })
