import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
// dev server 把 /api 请求代理到后端 FastAPI，解决开发期跨域；
// 生产环境由 FastAPI 同源托管 dist。
//
// ⚠️ 代理目标默认是 **dev 后端端口 8001**，不是生产的 8000。
//    原因：8000 是用户的 user systemd 服务（~/.config/systemd/user/
//    easy-tdx.service，Restart=always），且 EASY_TDX_WEB_DIST 指向
//    web-ui/dist（构建产物）。开发时打 8000 会 ① 与生产抢端口
//    ② 看到的是旧的构建产物，改 .vue 不生效。
//    dev 后端由 scripts/dev_backend.sh 起（8001，--reload）。
//    要用生产后端：VITE_API_PORT=8000 npm run dev
const devApiPort = process.env.VITE_API_PORT || '8001'

// 审计专用入口：mmd-e2e.html 让 Playwright 能挂载**真实 ChanlunChart.vue**
// 做买卖点标记的像素级验证（scripts/e2e_mmd_real_component.py）。
// 默认不构建，只在 CHANLUN_E2E=1 时加入 —— 避免审计页混进生产 dist。
const buildE2E = process.env.CHANLUN_E2E === '1'

// ⚠️ 域名白名单：Vite 8 起 server.allowedHosts 未显式列出的一律 403
//    "Blocked request. This host ... is not allowed"（防 DNS rebinding）。
//    本机由 NPM（docker: nginx-proxy-manager）按域名反代到 3012，且 **Host 头
//    原样透传**（见 /mnt/docker/nginxproxymanager/npm_new_data/nginx/proxy_host/
//    60.conf，未写 header_up Host），所以每个指到 3012 的 ppamoy.fun 子域名
//    都必须在这里放行，否则用户浏览器看到的就是那句 403。
//    已知入口（NPM proxy_host）：
//      easy.ppamoy.fun → 3012（easy_tdx 前端）
//      cl.ppamoy.fun   → 3012（缠论 dev 入口，NPM host 60）  ← 2026-10-12 报的 403
//      api.ppamoy.fun  → 8000（后端；反代时 header_up Host 被重写，不经过这里）
//    前缀点 '.ppamoy.fun' 是 Vite 的子域通配（源码 vite/dist/node/chunks/node.js:
//    isHostAllowedInternal），命中 ppamoy.fun 本身及所有 *.ppamoy.fun —— 这样以后
//    再挂新子域名不用每个都来改这儿再重启。
//    改完 vite 会自动重启（它监听 vite.config.ts），但**必须实测**，别只看配置：
//      bash scripts/check_dev_hosts.sh
const allowedHosts: string[] = [
  '.ppamoy.fun', // 通配：ppamoy.fun 及所有 *.ppamoy.fun 子域名
  'easy.ppamoy.fun',
  'api.ppamoy.fun',
  'cl.ppamoy.fun',
  'ppamoy.fun',
]

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
        target: `http://127.0.0.1:${devApiPort}`,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
    },
    allowedHosts,
  },
})
