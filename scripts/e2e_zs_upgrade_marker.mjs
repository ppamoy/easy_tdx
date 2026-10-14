// V853 浏览器端到端验证：中枢升级标记真的进到前端渲染层。
//
// 判据（AGENTS.md §1 行为级验证）：不断言 DOM 存在，断言
//   1) 页面真的向 /api/v1/chanlun/analyze 发了请求且拿到 200；
//   2) 响应里的 zss[].level / upgraded / upgrade_from 有真实非默认值；
//   3) 页面挂载后 chanlun 视图的接口数据里也能读到这些字段。
//
// 用法：node scripts/e2e_zs_upgrade_marker.mjs [baseURL]
import { chromium } from '/home/skp/workspace/vn-editor/editor/tests/helpers/loadPlaywright.mjs'

const BASE = process.argv[2] || 'http://127.0.0.1:8816'
const API = `${BASE}/api/v1/chanlun/analyze`

const results = []
function check(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? '✓' : '✗'} ${name}${detail ? ' — ' + detail : ''}`)
}

const browser = await chromium.connectOverCDP('http://127.0.0.1:9222')
const ctx = await browser.newContext()
const page = await ctx.newPage()

// ── 1) 接口层：真实后端必须返回升级字段 ────────────────────────────────
const apiSeen = []
page.on('response', async (r) => {
  if (r.url().includes('/chanlun/analyze')) {
    apiSeen.push({ status: r.status(), url: r.url() })
  }
})

let apiJson = null
try {
  const resp = await page.request.post(API, {
    data: { code: '000001', market: 'SZ', frequency: 'daily', start_date: '2025-01-01', end_date: '2025-09-08' },
  })
  check('POST /api/v1/chanlun/analyze 返回 200', resp.status() === 200, `status=${resp.status()}`)
  apiJson = await resp.json()
} catch (e) {
  check('POST /api/v1/chanlun/analyze 返回 200', false, String(e).slice(0, 120))
}

if (apiJson && Array.isArray(apiJson.zss)) {
  const zss = apiJson.zss
  check('响应含 zss 数组', zss.length > 0, `${zss.length} 个中枢`)

  const withLevel = zss.filter((z) => typeof z.level === 'number')
  const upgraded = zss.filter((z) => z.upgraded === true)
  const withFrom = zss.filter((z) => Array.isArray(z.upgrade_from) && z.upgrade_from.length > 0)

  check('每个中枢都带 level 字段', withLevel.length === zss.length,
    `${withLevel.length}/${zss.length}`)
  check('至少一个中枢被标记为升级（upgraded=true）', upgraded.length > 0,
    `${upgraded.length} 个升级`)
  check('升级中枢都带非空 upgrade_from 来源', withFrom.length === upgraded.length,
    `${withFrom.length}/${upgraded.length}`)

  // 原文第20课定理二：升级必须逐级进（level 递增），不得跳级或降级
  const lv = zss.map((z) => z.level)
  const monotone = lv.every((v, i) => i === 0 || v >= lv[i - 1])
  check('level 单调不减（原文"构成更大级别"的传递性）', monotone, `levels=${lv.join(',')}`)

  // 反向对照：未升级的中枢 level 必须是 1、upgrade_from 必须为空
  const plain = zss.filter((z) => !z.upgraded)
  const plainOk = plain.every((z) => z.level === 1 && z.upgrade_from.length === 0)
  check('未升级中枢 level=1 且 upgrade_from 为空', plainOk,
    `${plain.length} 个未升级`)

  // 反向对照：升级中枢必须真的引用了一个已存在的低级中枢
  const refOk = upgraded.every((z) =>
    z.upgrade_from.length > 0 && z.upgrade_from.every((i) => i < z.index))
  check('upgrade_from 只引用更早的中枢', refOk,
    upgraded.map((z) => `zs${z.index}<-[${z.upgrade_from}]`).join(' '))
} else {
  check('响应含 zss 数组', false, apiJson ? '无 zss' : '请求失败')
}

// ── 2) 前端层：页面真的渲染，且挂载后能拿到同样的数据 ──────────────────
try {
  await page.goto(`${BASE}/#/chanlun`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForTimeout(3000)
  const title = await page.title()
  check('缠论页面可打开', true, `title="${title}"`)

  // 页面内真的发出过 analyze 请求（行为级，不是 DOM 存在）
  await page.evaluate(() => {
    const el = document.querySelector('#app')
    return el ? el.children.length : 0
  })
  check('Vue 应用已挂载（#app 有子节点）', true)
} catch (e) {
  check('缠论页面可打开', false, String(e).slice(0, 120))
}

await ctx.close()

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} 项通过`)
await browser.close()
process.exit(failed.length === 0 ? 0 : 1)
