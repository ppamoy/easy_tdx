#!/usr/bin/env node
/**
 * 「买卖点核对」页（/signal-check）端到端行为验证。
 *
 * 纪律依据（~/.dsh/AGENTS.md §1）：不许用「DOM 里存在控件」冒充验证。
 * 本脚本断言的是**真实行为**：
 *   1. 页面加载后真的发出了 /api/v1/bars 与 /api/v1/chanlun/analyze，且都 200
 *   2. 分析结果里真的有 mmds，且渲染出「最新买卖点提示」卡片（不是空态）
 *   3. 命中率表格真的有行，且**随机基准列不是空的**（否则"有效"结论无意义）
 *   4. 切换周期后**重新发了请求**（参数真的生效，不是摆设）
 *
 * 用法：node scripts/check_signal_check_page.cjs [--url http://127.0.0.1:8000]
 */

const { chromium } = require('playwright')

const BASE = process.argv.includes('--url')
  ? process.argv[process.argv.indexOf('--url') + 1]
  : 'http://127.0.0.1:8000'
const CDP = 'http://127.0.0.1:9222'

const results = []
function check(name, ok, detail) {
  results.push({ name, ok, detail })
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ' — ' + detail : ''}`)
}

;(async () => {
  let browser
  try {
    browser = await chromium.connectOverCDP(CDP)
  } catch (e) {
    console.error('无法连接浏览器 CDP，请先 ~/.local/bin/moli-serve-start')
    process.exit(2)
  }
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await ctx.newPage()

  const seen = { bars: [], analyze: [], stats: [] }
  page.on('response', async (r) => {
    const u = r.url()
    try {
      if (u.includes('/api/v1/bars')) seen.bars.push({ status: r.status(), url: u })
      if (u.includes('/chanlun/analyze')) seen.analyze.push({ status: r.status(), url: u })
      if (u.includes('/chanlun/signal-stats')) seen.stats.push({ status: r.status(), url: u })
    } catch {}
  })

  const errors = []
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })

  // ── 1. 打开页面 ──
  await page.goto(`${BASE}/signal-check`, { waitUntil: 'domcontentloaded', timeout: 45000 })
  // ⚠️ 必须等到加载完成：缠论分析是同步重计算（后端 750 根约 3~6s），
  //    只等 3s 会读到「加载中…」的空态，把**能正常工作的页面**误判为失败。
  //    实测：3s 时 rows=0，6s 时 rows=6。这里按轮询等真正出结果。
  await page
    .waitForFunction(
      () => !document.body.innerText.includes('加载中'),
      { timeout: 30000 },
    )
    .catch(() => {})
  await page.waitForTimeout(1500)

  check('页面打开无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '))
  check(
    '发出了 /api/v1/bars 请求且 200',
    seen.bars.length > 0 && seen.bars.some((b) => b.status === 200),
    JSON.stringify(seen.bars.slice(0, 2)),
  )
  check(
    '发出了 /chanlun/analyze 请求且 200',
    seen.analyze.length > 0 && seen.analyze.some((a) => a.status === 200),
    JSON.stringify(seen.analyze.slice(0, 2)),
  )

  check(
    '发出了 /chanlun/signal-stats 请求且 200（统计走后端唯一口径）',
    seen.stats.length > 0 && seen.stats.some((s) => s.status === 200),
    JSON.stringify(seen.stats.slice(0, 2)),
  )

  // ── 2. 最新买卖点卡片不是空态 ──
  const hasLatestCard = await page.evaluate(() => {
    const el = document.querySelector('.latest-body')
    return !!el && (el.textContent || '').trim().length > 0
  })
  const emptyState = await page.evaluate(() => {
    const els = [...document.querySelectorAll('.muted')]
    return els.some((e) => (e.textContent || '').includes('没有买卖点信号'))
  })
  check('渲染出「最新买卖点提示」卡片（非空态）', hasLatestCard, emptyState ? '命中空态文案' : '')

  // ── 3. 命中率表格有行，且随机基准列非空 ──
  const tbl = await page.evaluate(() => {
    const rows = [...document.querySelectorAll('.tbl tbody tr')]
    return rows.map((r) => [...r.querySelectorAll('td')].map((td) => td.textContent.trim()))
  })
  check('命中率表格有数据行', tbl.length > 0, `行数=${tbl.length}`)
  if (tbl.length) {
    // 列序：信号/前瞻/样本数/信号涨跌/随机基准/超额/结论
    const rndEmpty = tbl.filter((r) => r[4] === '' || r[4] === '—' || r[4] == null)
    check('随机基准列全部非空（否则"有效"结论无意义）', rndEmpty.length === 0,
      `空列行=${rndEmpty.length}`)
    const hasVerdict = tbl.filter((r) => r[6] && r[6].length > 0)
    check('每行都有结论（显著/不显著/方向错）', hasVerdict.length === tbl.length,
      `${hasVerdict.length}/${tbl.length}`)
    // 关键：样本数必须**真的显示出来**（n=1 的百分比是误导）
    const hasCount = tbl.filter((r) => /^\d+$/.test(r[2] || ''))
    check('每行都显示样本数（n 小的行要能看出不足为凭）', hasCount.length === tbl.length,
      `${hasCount.length}/${tbl.length}`)
    console.log('   表格首行:', JSON.stringify(tbl[0]))
    // 小样本警告
    const warn = await page.evaluate(() =>
      [...document.querySelectorAll('.warn')].map((e) => e.textContent.trim()).join(' | '))
    if (warn) console.log('   页面警告:', warn.slice(0, 160))
  }

  // ── 4. 切换周期真的重新发请求 ──
  const before = seen.analyze.length
  // ⚠️ 第一个 select 是周期，第二个是时间范围。选错就测不到「切换周期」
  //    （实测选到范围下拉时请求数不变，误报失败）。
  const selects = await page.$$('.ctrl select')
  check('页面上至少有两个下拉（周期 + 范围）', selects.length >= 2, `实际 ${selects.length} 个`)
  const opts = await page.evaluate(() => {
    const sels = [...document.querySelectorAll('.ctrl select')]
    return sels.map((s) => [...s.options].map((o) => o.value))
  })
  console.log('   下拉选项:', JSON.stringify(opts))
  // ⚠️ Moli 上 Playwright 的 selectOption() **不会**触发 Vue 的 v-model
  //    （实测：selectOption 后请求数不变；原生 dispatchEvent('change') 后 1→2，
  //     且周期标签真的变成「30分钟」）。这是浏览器底座的限制，不是页面 bug，
  //     所以用原生事件派发来断言「切换真的生效」。
  await page.evaluate(() => {
    const sel = document.querySelectorAll('.ctrl select')[0]
    sel.value = 'MIN_30'
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  })
  // ⚠️ 先等「加载中」**出现**（请求已发出），再等它消失（请求完成）。
  //    只等消失会在请求还没发起时就返回（此刻文本仍是旧的不含"加载中"），
  //    于是断言早于请求发出 ⇒ 误报失败。实测修好后 1→2。
  await page
    .waitForFunction(() => document.body.innerText.includes('加载中'), { timeout: 15000 })
    .catch(() => {})
  await page
    .waitForFunction(() => !document.body.innerText.includes('加载中'), { timeout: 45000 })
    .catch(() => {})
  await page.waitForTimeout(1000)
  check('切换周期后重新发了 analyze 请求', seen.analyze.length > before,
    `${before} → ${seen.analyze.length}`)
  const lastAnalyze = seen.analyze[seen.analyze.length - 1]
  check('切换后 analyze 仍成功', lastAnalyze && lastAnalyze.status === 200,
    JSON.stringify(lastAnalyze))
  const rangeAfter = await page.evaluate(() => document.querySelector('.range')?.textContent ?? '')
  check('切换后周期标签真的变成 30分钟', rangeAfter.includes('30分钟'), rangeAfter)

  // ── 截图 ──
  await page.screenshot({ path: '/tmp/signal-check.png', fullPage: true })
  console.log('   截图: /tmp/signal-check.png')

  await ctx.close()
  await browser.close()

  const failed = results.filter((r) => !r.ok)
  console.log(`\n${failed.length ? '❌' : '✅'} ${results.length - failed.length}/${results.length} 通过`)
  process.exit(failed.length ? 1 : 0)
})().catch((e) => {
  console.error('异常:', e.message)
  process.exit(2)
})
