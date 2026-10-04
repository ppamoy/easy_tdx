import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
// dev server 把 /api 请求代理到后端 FastAPI（默认 8000 端口），
// 解决开发期跨域；生产环境由 FastAPI 同源托管 dist。

// 审计专用入口：mmd-e2e.html 让 Playwright 能挂载**真实 ChanlunChart.vue**
// 做买卖点标记的像素级验证（scripts/e2e_mmd_real_component.py）。
// 默认不构建，只在 CHANLUN_E2E=1 时加入 —— 避免审计页混进生产 dist。
const buildE2E = process.env.CHANLUN_E2E === '1'
// ⚠️ 显式标注为 Record<string,string>：三元里 `mmdE2e` 一支可能不存在，
//    TS 推成 `{main;mmdE2e?:undefined}`，与 rollup 的
//    `InputOption | Record<string,string>` 重载不匹配而报 TS2769。
const rollupInput: Record<string, string> = buildE2E
  ? { main: 'index.html', mmdE2e: 'mmd-e2e.html' }
  : { main: 'index.html' }

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: { input: rollupInput },
  },
  server: {
    host: '0.0.0.0',
    port: 3012,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
    allowedHosts: ['easy.ppamoy.fun', 'api.ppamoy.fun', 'ppamoy.fun'],
  },
})
