// 行为级验证（§1）：/signal-check 选次级别+点买卖点 → 次级别K线图渲染
// 断言：1) analyze请求真发出 2) multi-level请求真发出 3) 买卖点明细渲染
//        4) 点买卖点后「次级别K线结构」section渲染
const { chromium } = require('/home/skp/.hermes/node/lib/node_modules/playwright')

;(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222')
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } })
  const page = await ctx.newPage()
  const reqs = []
  page.on('request', (r) => {
    const u = r.url()
    if (u.includes('/chanlun/analyze') || u.includes('/chanlun/multi-level')) reqs.push(u)
  })

  await page.goto('http://127.0.0.1:3012/signal-check', { waitUntil: 'networkidle' })
  // 选次级别 30min（用 title 属性精确定位）
  await page.locator('select[title*="次级别"]').selectOption('MIN_30')
  // 点「查看」按钮
  const btn = page.getByRole('button', { name: '查看' })
  await btn.click()
  // 等请求+渲染（multi-level 1y≈19s，给足）
  await page.waitForResponse((r) => r.url().includes('/chanlun/multi-level'), { timeout: 60000 }).catch(() => {})
  await page.waitForTimeout(2000)

  const analyzeOk = reqs.some((u) => u.includes('/chanlun/analyze'))
  const multiOk = reqs.some((u) => u.includes('/chanlun/multi-level'))
  // 买卖点明细行（class=tbl detail，区别于统计表 tbl stats）
  const rowCount = await page.locator('table.tbl.detail tbody tr').count().catch(() => 0)
  console.log('analyze请求发出:', analyzeOk)
  console.log('multi-level请求发出:', multiOk)
  console.log('买卖点明细行数:', rowCount)

  // 点第一行买卖点（明细表，非统计表）
  if (rowCount > 0) {
    await page.locator('table.tbl.detail tbody tr').first().click()
    await page.waitForTimeout(1500)
    // 截图看次级别图
    await page.screenshot({ path: '/tmp/signal_check_subchart.png', fullPage: true })
    // 断言「次级别K线结构」section 渲染（h3 文本）
    const subChartH = await page.getByText(/次级别.*K.*线.*结构|次级别结构/).count().catch(() => 0)
    console.log('次级别K线结构section渲染:', subChartH > 0)
    console.log('RESULT:', (analyzeOk && multiOk && rowCount > 0 && subChartH > 0) ? 'PASS' : 'FAIL')
  } else {
    console.log('RESULT: FAIL(无买卖点明细行)')
  }
  await ctx.close()
  await browser.close()
})().catch((e) => { console.error(e); process.exit(1) })
