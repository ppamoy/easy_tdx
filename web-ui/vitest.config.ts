import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// vitest 统一测试运行器配置（V389 引入）。
// 与 vite.config.ts 分离：vitest 不需要 dev server 代理等配置，
// 且 jsdom 环境只需在测试时加载。
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    // 组件测试用 DOM 断言，globals 显式关闭，测试文件自行 import { test, expect }。
    globals: false,
  },
})
