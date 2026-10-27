import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { unlink } from 'node:fs/promises'
import { resolve } from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
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
    // 공개 API는 core-service만 호출 (compose 실행 시 localhost:8080, CORE_HOST_PORT로 변경 가능)
    proxy: {
      '/api': `http://localhost:${process.env.CORE_HOST_PORT ?? 8080}`,
    },
  },
})
