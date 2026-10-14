// dev 环境全页面健康扫描：过 CDP 连 Moli，逐页收集 console error / pageerror
// / 4xx-5xx 请求 / failed 请求，输出 JSON 报告。
//
// 用法:
//   node scripts/dev_scan_pages.cjs                 # 扫所有页面
//   node scripts/dev_scan_pages.cjs / /signal-check # 只扫指定路径
//
// 出口码：发现 console error（白名单外）或 4xx/5xx 或 failed 请求 → 1
//
// ⚠️ Moli 注意（实测）：
//   - `moli serve` 必须带 --layout，否则 click/screenshot 不可用（本脚本只用
//     goto/evaluate，不依赖布局，但仍建议通过 moli-serve-start 启动）。
//   - 长跑会退化：无法解释的失败先 moli-serve-start --restart。

const { chromium } = require('playwright')

const BASE = process.env.DEV_SCAN_BASE || 'http://127.0.0.1:3012'
const CDP = process.env.DEV_SCAN_CDP || 'http://127.0.0.1:9222'

const ALL_PAGES = [
  '/',
  '/learn',
  '/backtest',
  '/signal-check',
  '/strategies',
  '/optimize',
  '/portfolio',
  '/compare',
  '/screening',
  '/fundamental',
  '/changying',
  '/diagnosis',
  '/monitor',
  '/today',
  '/stock-pick',
  '/audit',
  '/settings',
  '/display-settings',
]

// 已知无害、不算失败的噪声（按 substring 匹配）
const CONSOLE_IGNORE = [
  'favicon',
  'Failed to load resource: the server responded with a status of 404 (Not Found)',
  'Download the Vue Devtools',
  '[vite] connecting',
  '[vite] connected',
]

// 404 且非 API 的不算问题（如缺失的静态资源）
const URL_IGNORE = ['favicon', '/@vite/', '/node_modules/']

function ignored(text) {
  return CONSOLE_IGNORE.some((s) => text.includes(s))
}

async function scanPage(ctx, path) {
  const page = await ctx.newPage()
  const consoleErrors = []
  const pageErrors = []
  const badResponses = []
  const failedRequests = []

  page.on('console', (msg) => {
    if (msg.type() !== 'error' && msg.type() !== 'warning') return
    const t = msg.text()
    if (msg.type() === 'error' && !ignored(t)) consoleErrors.push(t)
  })
  page.on('pageerror', (e) => pageErrors.push(String(e && e.message ? e.message : e)))
  page.on('response', (resp) => {
    const status = resp.status()
    if (status >= 400) {
      const url = resp.url()
      if (!URL_IGNORE.some((s) => url.includes(s))) {
        badResponses.push({ status, url, method: resp.request().method() })
      }
    }
  })
  page.on('requestfailed', (req) => {
    const url = req.url()
    if (!URL_IGNORE.some((s) => url.includes(s))) {
      failedRequests.push({ url, method: req.method(), err: String(req.failure() && req.failure().errorText) })
    }
  })

  let navErr = null
  try {
    await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 60000 })
  } catch (e) {
    navErr = String(e && e.message ? e.message : e)
  }
  // 给异步请求 + 首屏渲染一点时间
  await page.waitForTimeout(6000)

  await page.close()
  return { path, navErr, consoleErrors, pageErrors, badResponses, failedRequests }
}

;(async () => {
  const paths = process.argv.slice(2).length ? process.argv.slice(2) : ALL_PAGES
  const browser = await chromium.connectOverCDP(CDP)
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })

  const report = []
  for (const p of paths) {
    const r = await scanPage(ctx, p)
    report.push(r)
    const bad = r.navErr || r.consoleErrors.length || r.pageErrors.length || r.badResponses.length || r.failedRequests.length
    console.log(`${bad ? '❌' : '✅'} ${p}` +
      (r.navErr ? ` nav=${r.navErr}` : '') +
      (r.consoleErrors.length ? ` console=${r.consoleErrors.length}` : '') +
      (r.pageErrors.length ? ` pageerror=${r.pageErrors.length}` : '') +
      (r.badResponses.length ? ` http=${r.badResponses.length}` : '') +
      (r.failedRequests.length ? ` failed=${r.failedRequests.length}` : ''))
  }

  const fs = require('fs')
  const outFile = process.env.DEV_SCAN_OUT || '/tmp/dev_scan_report.json'
  fs.writeFileSync(outFile, JSON.stringify(report, null, 2))
  console.log(`\n报告已写入: ${outFile}`)

  await ctx.close()
  const total =
    report.reduce(
      (n, r) => n + (r.navErr ? 1 : 0) + r.consoleErrors.length + r.pageErrors.length + r.badResponses.length + r.failedRequests.length,
      0,
    )
  console.log(`\nTOTAL_ISSUES=${total}`)
  process.exit(total ? 1 : 0)
})().catch((e) => {
  console.error('FATAL', e)
  process.exit(2)
})
