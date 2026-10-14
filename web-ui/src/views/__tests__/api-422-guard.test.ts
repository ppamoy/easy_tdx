// 422 防御的牙齿测试。
//
// 背景（实测 2026-10-10）：用户在控制台看到
//   `api.ts:374  POST /api/v1/backtest/run 422 (Unprocessable Entity)`
// 后端返回 `{"detail":[{"type":"missing","loc":["body","strategy"],
//            "msg":"Field required"}]}`
// —— strategy 是 BacktestRequest 的必填字段，来源是「已保存策略」重验路径
//    里 localStorage 旧记录没有该字段，直传就 422，用户只看到裸 422。
//
// 同时后端 /bars 的 count 是 Query(800, ge=1, le=800)（bars.py:74，
// TDX 协议单页上限），日志里出现过 `count=4000` / `count=2000` →
// 422 less_than_equal(le=800)。
//
// 这两条都是「参数层契约」，文档拦不住，锁成断言。
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi, afterEach } from 'vitest'

// api.ts 在模块加载时读 BASE，测试里只需 guard 逻辑，不真发请求。
const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

const { runBacktest } = await import('../../api')

afterEach(() => {
  fetchMock.mockReset()
})

describe('runBacktest 的 strategy 必填预校验', () => {
  it('strategy 为空时**不发请求**直接抛可读错误（不再裸 422）', async () => {
    await expect(
      runBacktest({ strategy: '' } as never),
    ).rejects.toThrow(/缺少 strategy/)
    // 关键：请求根本没发出去
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('strategy 为 undefined 时同样拦截', async () => {
    await expect(
      runBacktest({} as never),
    ).rejects.toThrow(/缺少 strategy/)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('strategy 正常时照常发请求（对照组：不能误伤正常路径）', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({}),
    })
    await runBacktest({ strategy: 'ma_cross' } as never)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('fetchBars 单页 count 不超过后端 le=800', () => {
  it('源码里 /bars 的 count 被钳到 800（不能写死更大值）', async () => {
    // jsdom 环境下 import.meta.url 不是 file: scheme（实测
    // ERR_INVALID_URL_SCHEME），改用 cwd 相对路径（vitest 从 web-ui 根跑）。
    const src = readFileSync(resolve(process.cwd(), 'src/api.ts'), 'utf8')
    // 必须引用 MAX_BARS_PER_PAGE 做钳制
    expect(src).toContain('MAX_BARS_PER_PAGE')
    expect(src).toMatch(/const perPage = Math\.min\(800,\s*MAX_BARS_PER_PAGE\)/)
    // 不能出现裸写 count: '4000' 之类超过 800 的字面量
    expect(src).not.toMatch(/count:\s*'(?!800')\d{4,}'/)
  })
})
