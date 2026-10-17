// 验证多级别联立同屏双图 + 区间套三态 overlay（行为级，§1）。
// 检查 window.__CHANLUN_CHARTS__（按 frequency 键：DAY=高级别, MIN_30=低级别）。
// 每张图报告：barCount(K线)/biCount(笔)/buyCount+sellCount(买卖点)/overlay(区间套三态)。
// 用法: CHANLUN_BASE=http://127.0.0.1:8001 node scripts/verify_qt_overlay.mjs
import { chromium } from '/home/skp/workspace/chuma-xian-game/node_modules/playwright/index.mjs';

const BASE = process.env.CHANLUN_BASE ?? 'http://127.0.0.1:8001';
const CODE = process.env.CHANLUN_CODE ?? '600000';

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const page = await browser.newPage({ viewport: { width: 1680, height: 2200 } });

const errs = [];
page.on('pageerror', (e) => errs.push(e.message));
const reqLog = [];
page.on('requestfailed', (r) => reqLog.push(r.url()));

// /chanlun 重定向到 /learn?tab=analysis（丢 query），直接去目标并带 chartDebug
await page.goto(BASE + '/learn?tab=analysis&chartDebug=1', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('.chanlun-view', { timeout: 30000 }).catch(() => {});
await page.fill('.config-bar input[type="text"]', CODE).catch(() => {});
await page.selectOption('.config-bar select', 'DAY').catch(() => {});
await page.fill('.config-bar input[type="number"]', '300').catch(() => {});
// 多级别联立（区间套 + 低级别同屏数据来源）
await page.check('.config-bar input[type="checkbox"]').catch(() => {});
await page.click('.analyze-btn').catch(() => {});
await page.waitForFunction(
  () => !!document.querySelector('.stats-bar') || !!document.querySelector('.error-banner'),
  { timeout: 150000 },
).catch(() => {});

// 等 chart map 挂上 window（最多 25s——低级别 fetchBars + 映射需时间）
await page.waitForFunction(
  () => !!(window).__CHANLUN_CHARTS__ && Object.keys(window.__CHANLUN_CHARTS__).length >= 2,
  { timeout: 25000 },
).catch(() => {});

const result = await page.evaluate(() => {
  function inspectChart(ch, freq) {
    const opt = ch.getOption();
    const series = opt.series || [];
    let barCount = 0, biCount = 0, xdCount = 0, zsCount = 0, buyCount = 0, sellCount = 0;
    const mps = [];
    for (const s of series) {
      const data = s.data;
      if (!Array.isArray(data)) continue;
      if (s.type === 'candlestick') barCount = data.length;
      if (s.name === '笔(虚线)') biCount = data.length;
      if (s.name === '线段(实线)') xdCount = data.length;
      if (s.name === '中枢') zsCount = data.length;
      if (s.name === '买点') buyCount = data.length;
      if (s.name === '卖点') sellCount = data.length;
      for (const d of data) {
        const it = d.itemStyle || {};
        const lb = d.label || {};
        if (it.borderColor && lb.show && lb.formatter) {
          mps.push({ border: it.borderColor, mark: lb.formatter });
        }
      }
    }
    const states = {}, marks = {};
    for (const m of mps) { states[m.border] = (states[m.border] || 0) + 1; marks[m.mark] = (marks[m.mark] || 0) + 1; }
    return { freq, barCount, biCount, xdCount, zsCount, buyCount, sellCount, overlay: mps.length, byBorderColor: states, byMark: marks };
  }
  const map = window.__CHANLUN_CHARTS__;
  if (!map || Object.keys(map).length === 0) {
    const ch = window.__CHANLUN_CHART__;
    if (!ch) return { hasCharts: false, reason: 'window.__CHANLUN_CHARTS__ 未挂载' };
    return { hasCharts: true, charts: { single: inspectChart(ch, 'single') } };
  }
  const out = {};
  for (const [freq, ch] of Object.entries(map)) out[freq] = inspectChart(ch, freq);
  return { hasCharts: true, charts: out };
});

const panelPresent = await page.evaluate(() => {
  const diagCards = Array.from(document.querySelectorAll('.mmd-diag-card'));
  const actions = diagCards.map((c) => c.querySelector('.mmd-diag-action')?.textContent?.trim() ?? '');
  const actionCount = {};
  for (const a of actions) actionCount[a] = (actionCount[a] || 0) + 1;
  return {
    multiPanel: !!document.querySelector('.multi-level-panel'),
    lowChart: !!document.querySelector('.ml-low-chart'),
    lowChartCanvas: !!document.querySelector('.ml-low-chart canvas'),
    diagPanel: !!document.querySelector('.mmd-diagnosis-panel'),
    diagCards: diagCards.length,
    actions: actionCount,
    diagSample: diagCards.slice(0, 3).map((c) => ({
      type: c.querySelector('.mmd-diag-type')?.textContent?.trim(),
      action: c.querySelector('.mmd-diag-action')?.textContent?.trim(),
      hasQtBadge: !!c.querySelector('.qt-badge'),
      stop: c.querySelector('.mmd-diag-stop')?.textContent?.trim(),
    })),
    errorBanner: document.querySelector('.error-banner')?.textContent?.trim() ?? '',
  };
});

console.log(JSON.stringify({ pageErrors: errs, failedRequests: reqLog, panel: panelPresent, ...result }, null, 2));
await browser.close();
