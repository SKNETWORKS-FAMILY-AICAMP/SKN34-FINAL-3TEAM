import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 공개 API는 core-service만 호출 (compose 실행 시 localhost:8080, CORE_HOST_PORT로 변경 가능)
    proxy: {
      '/api': `http://localhost:${process.env.CORE_HOST_PORT ?? 8080}`,
    },
  },
})
