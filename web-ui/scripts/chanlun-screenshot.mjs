
// 缠论图表浏览器测试 v3：打开 /chanlun，等待分析完成，检查图表内部渲染状态并截图。
// 用法: node scripts/chanlun-screenshot.mjs [code] [category] [count] [outDir]
import { chromium } from '/home/skp/workspace/chuma-xian-game/node_modules/playwright/index.mjs';
import fs from 'fs';
import path from 'path';

const BASE = process.env.CHANLUN_BASE ?? 'http://127.0.0.1:3012';
const [, , codeArg, categoryArg, countArg, outDirArg] = process.argv;
const CODE = codeArg ?? '000001';
const CATEGORY = categoryArg ?? 'DAY';
const COUNT = countArg ?? '800';
const OUT = outDirArg ?? '/tmp/chanlun_shots';
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const page = await browser.newPage({ viewport: { width: 1680, height: 2400 } });
const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];
const apiResponses = {};

page.on('console', (msg) => {
  if (msg.type() === 'error' || msg.type() === 'warning') consoleErrors.push(`[${msg.type()}] ${msg.text()}`);
});
page.on('pageerror', (err) => pageErrors.push(err.message));
page.on('requestfailed', (req) => failedRequests.push(`${req.method()} ${req.url()} :: ${req.failure()?.errorText}`));
page.on('response', async (resp) => {
  const u = resp.url();
  if (u.includes('/api/v1/chanlun/')) {
    try {
      const json = await resp.json();
      apiResponses[u.includes('multi-level') ? 'multi-level' : 'analyze'] = json;
    } catch {}
  }
});

await page.goto(BASE + '/chanlun', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('.chanlun-view', { timeout: 30000 }).catch(() => {});

await page.fill('.config-bar input[type="text"]', CODE).catch(() => {});
await page.selectOption('.config-bar select', CATEGORY).catch(() => {});
await page.fill('.config-bar input[type="number"]', COUNT).catch(() => {});
if (process.env.CHANLUN_MULTI === '1') {
  await page.check('.config-bar input[type="checkbox"]').catch(() => {});
}
await page.click('.analyze-btn').catch(() => {});

await page.waitForFunction(() => !!document.querySelector('.stats-bar') || !!document.querySelector('.error-banner'), { timeout: 150000 }).catch(() => {});
await page.waitForTimeout(3000);

const tag = `${CODE}_${CATEGORY}_${COUNT}`;
await page.screenshot({ path: path.join(OUT, `full_${tag}.png`), fullPage: true });
const chartEl = await page.$('.chart-area');
if (chartEl) {
  await chartEl.screenshot({ path: path.join(OUT, `chart_${tag}.png`) });
}

const statsText = await page.evaluate(() => {
  const els = document.querySelectorAll('.stat-item');
  const out = {};
  els.forEach((el) => {
    const label = el.querySelector('.stat-label')?.textContent?.trim();
    const value = el.querySelector('.stat-value')?.textContent?.trim();
    if (label) out[label] = value;
  });
  return { stats: out, error: document.querySelector('.error-banner')?.textContent?.trim() ?? '', mmdRows: document.querySelectorAll('.mmd-list tbody tr').length };
});

// ── 图表内部状态检查 ──
const chartInfo = await page.evaluate(() => {
  const out = { hasHook: false };
  const chart = (window).__CHANLUN_CHART__;
  if (!chart) return out;
  out.hasHook = true;
  const opt = chart.getOption();
  const series = opt?.series ?? [];
  out.seriesNames = series.map((s) => s.name);
  const find = (n) => series.find((s) => s.name === n);
  const biS = find('笔(虚线)'), xdS = find('线段(实线)'), zsS = find('中枢');
  const fxS = find('分型'), mmdS = find('买卖点'), bcS = find('背驰');
  out.biMarkLineCount = biS?.markLine?.data?.length ?? 0;
  out.xdMarkLineCount = xdS?.markLine?.data?.length ?? 0;
  out.zsMarkAreaCount = zsS?.markArea?.data?.length ?? 0;
  out.fxScatterCount = fxS?.data?.length ?? 0;
  out.mmdScatterCount = mmdS?.data?.length ?? 0;
  out.bcScatterCount = bcS?.data?.length ?? 0;
  out.xAxisLen = opt?.xAxis?.[0]?.data?.length ?? 0;
  const xlen = out.xAxisLen;
  out.mmdBadCoords = (mmdS?.data ?? []).map((d) => d[0]).filter((x) => x < 0 || x >= xlen || !Number.isFinite(x)).length;
  out.mmdCoordSample = (mmdS?.data ?? []).slice(0, 18).map((d, i) => [i, d[0]]);
  out.legend = opt?.legend?.[0]?.data ?? [];
  // 分型/买卖点/背驰 label formatter 抽样（取前3个文本）
  const sampleLabels = (s) => {
    if (!s || !s.data) return [];
    const f = s.label?.formatter;
    if (typeof f !== 'function') return [];
    return s.data.slice(0, 3).map((d, i) => f({ dataIndex: i }));
  };
  out.fxLabelSample = sampleLabels(fxS);
  out.mmdLabelSample = sampleLabels(mmdS);
  out.bcLabelSample = sampleLabels(bcS);
  return out;
});

// 缩放到最近 150 根做细节截图
await page.evaluate(() => {
  const chart = (window).__CHANLUN_CHART__;
  if (chart) {
    const opt = chart.getOption();
    const xlen = opt?.xAxis?.[0]?.data?.length ?? 800;
    const start = Math.max(0, 100 - (140 / xlen) * 100);
    chart.dispatchAction({ type: 'dataZoom', start, end: 100 });
  }
});
await page.waitForTimeout(1600);
await page.screenshot({ path: path.join(OUT, `zoom_${tag}.png`) });
const chartEl2 = await page.$('.chart-area');
if (chartEl2) {
  await chartEl2.screenshot({ path: path.join(OUT, `zoom_chart_${tag}.png`) });
}

const analyze = apiResponses['analyze'];
const result = {
  tag,
  url: page.url(),
  statsText,
  chartInfo,
  apiSummary: analyze ? {
    kline_count: analyze.kline_count,
    fractal_count: analyze.fractal_count,
    bi_count: analyze.bi_count,
    xd_count: analyze.xd_count,
    zs_count: analyze.zs_count,
    mmd_count: analyze.mmd_count,
    bc_count: analyze.bc_count,
    mmdTypes: (analyze.mmds ?? []).map((m) => m.type),
  } : null,
  apiBars: analyze?.bis?.length,
  consoleErrors: consoleErrors.slice(0, 30),
  pageErrors: pageErrors.slice(0, 10),
  failedRequests: failedRequests.slice(0, 10),
};
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));

await browser.close();
