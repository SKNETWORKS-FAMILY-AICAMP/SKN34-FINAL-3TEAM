import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { deviceDemoPlugin } from './scripts/device-demo-plugin.ts'
import { paymentTestPlugin } from './scripts/payment-test-plugin.ts'
import { unlink } from 'node:fs/promises'
import { resolve } from 'node:path'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Read the repository .env, but explicitly expose ONLY the public client key.
  const env = { ...loadEnv(mode, process.env.TOSSPAYMENTS_ENV_DIR || resolve(process.cwd(), '../..'), ''), ...loadEnv(mode, process.cwd(), ''), ...process.env }
  const paymentTest = mode === 'payment-test'
  const qrDemo = mode === 'qr-demo' || (env.VITE_API_MOCK === 'true' && env.VITE_SHARED_DEVICE_MOCK === 'true')
  return {
  define: {
    'import.meta.env.VITE_TOSSPAYMENTS_CLIENT_KEY': JSON.stringify(env.TOSSPAYMENTS_CLIENT_KEY || ''),
    'import.meta.env.VITE_TOSS_TEST_BILLING_CLIENT_KEY': JSON.stringify(env.TOSS_TEST_BILLING_CLIENT_KEY || ''),
    'import.meta.env.VITE_PAYMENT_TEST': JSON.stringify(paymentTest ? 'true' : 'false'),
    ...(qrDemo || paymentTest ? { 'import.meta.env.VITE_API_MOCK': JSON.stringify('true') } : {}),
    ...(qrDemo ? { 'import.meta.env.VITE_SHARED_DEVICE_MOCK': JSON.stringify('true') } : {}),
  },
  plugins: [
    paymentTestPlugin(paymentTest, env.TOSSPAYMENTS_SECRET_KEY || ''),
    deviceDemoPlugin(qrDemo),
    react(),
    tailwindcss(),
    {
      name: 'exclude-development-worker',
      apply: 'build',
      async writeBundle(options) {
        // public/의 개발 worker만 빌드 복사본에서 제외한다. 원본과 다른 산출물은 보존한다.
        if (options.dir)
          await unlink(resolve(options.dir, 'mockServiceWorker.js')).catch((error) => {
            if (error.code !== 'ENOENT') throw error
          })
      },
    },
  ],
  server: {
    ...(paymentTest ? { host: '127.0.0.1', strictPort: true } : {}),
    // 공개 API는 core-service만 호출 (compose 실행 시 localhost:8080, CORE_HOST_PORT로 변경 가능)
    proxy: {
      '/api': `http://localhost:${process.env.CORE_HOST_PORT ?? 8080}`,
    },
  },
  }
})
