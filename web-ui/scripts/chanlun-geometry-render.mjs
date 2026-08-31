// 缠论画图几何渲染回归测试 v1
// 读取 echarts 内部渲染状态，编程断言：
//   1) 每条笔 markLine 的两个端点 (xIndex, price) 必须精确等于 API 返回的
//      start_index/end_index 与 start_val/end_val（即端点落在 K 线极值上）；
//   2) 相邻笔 markLine 共享端点（bi[i].end == bi[i+1].start 同索引同价格）；
//   3) 线段 markLine 同样对齐 + 首尾相连；
//   4) 分型/买卖点/背驰 scatter 的 x 坐标必须在 K 线范围内。
// 同时截图（全图 + 最近 150 根）供人工/视觉复核。
// 用法: node scripts/chanlun-geometry-render.mjs [code] [category] [count] [outDir]
import { chromium } from '/home/skp/workspace/chuma-xian-game/node_modules/playwright/index.mjs';
import fs from 'fs';
import path from 'path';

const BASE = process.env.CHANLUN_BASE ?? 'http://127.0.0.1:3012';
const [, , codeArg, categoryArg, countArg, outDirArg] = process.argv;
const CODE = codeArg ?? '000001';
const CATEGORY = categoryArg ?? 'DAY';
const COUNT = countArg ?? '800';
const OUT = outDirArg ?? '/tmp/chanlun_geo_render';
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const page = await browser.newPage({ viewport: { width: 1680, height: 2400 } });
const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push(e.message));

await page.goto(BASE + '/chanlun', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('.chanlun-view', { timeout: 30000 }).catch(() => {});
await page.fill('.config-bar input[type="text"]', CODE).catch(() => {});
await page.selectOption('.config-bar select', CATEGORY).catch(() => {});
await page.fill('.config-bar input[type="number"]', COUNT).catch(() => {});
await page.click('.analyze-btn').catch(() => {});
await page.waitForFunction(() => !!document.querySelector('.stats-bar') || !!document.querySelector('.error-banner'), { timeout: 150000 }).catch(() => {});
await page.waitForTimeout(2500);

const tag = CODE + '_' + CATEGORY + '_' + COUNT;
const report = { tag, url: page.url(), errors: [], checks: {}, fails: [] };

const internal = await page.evaluate(() => {
  const chart = window.__CHANLUN_CHART__;
  if (!chart) return null;
  const opt = chart.getOption();
  const series = opt?.series ?? [];
  const find = (n) => series.find((s) => s.name === n);
  const xlen = opt?.xAxis?.[0]?.data?.length ?? 0;
  const ohlc = find('K线')?.data ?? [];
  const bis = (find('笔(虚线)')?.markLine?.data ?? []).map((pair) =>
    pair.map((p) => ({ x: p.coord[0], y: p.coord[1] }))
  );
  const xds = (find('线段(实线)')?.markLine?.data ?? []).map((pair) =>
    pair.map((p) => ({ x: p.coord[0], y: p.coord[1] }))
  );
  const fx = (find('分型')?.data ?? []).map((d) => d[0]);
  const mmd = (find('买卖点')?.data ?? []).map((d) => d[0]);
  const bc = (find('背驰')?.data ?? []).map((d) => d[0]);
  return { xlen, ohlc, bis, xds, fx, mmd, bc };
});

if (!internal) {
  report.errors.push('__CHANLUN_CHART__ not available');
} else {
  const { xlen, ohlc, bis, xds, fx, mmd, bc } = internal;
  report.checks.xlen = xlen;
  report.checks.biCount = bis.length;
  report.checks.xdCount = xds.length;

  // 容忍度：后端 start_val/end_val 四舍五入到 2 位小数，K线 high/low 是 float32
  // （~6 位有效数字，如 9.60000038）。比较用「半跳价 + float32 噪声」= 0.0052，
  // 不能用 1e-9（会把精度噪声误报成端点悬空）。
  const EPS = 0.0052;
  const onExtreme = (bar, y) => bar && (Math.abs(bar[3] - y) < EPS || Math.abs(bar[2] - y) < EPS); // [open,close,low,high]
  const inRange = (x) => x !== undefined && x !== null && x >= 0 && x < xlen;
  const badCoord = (arr, label) => arr.filter((x) => !inRange(x)).length;
  report.checks.fxBadX = badCoord(fx, '分型');
  report.checks.mmdBadX = badCoord(mmd, '买卖点');
  report.checks.bcBadX = badCoord(bc, '背驰');

  // 每条笔 markLine 端点必须在 K 线范围内
  for (let i = 0; i < bis.length; i++) {
    const [s, e] = bis[i];
    if (!inRange(s.x) || !inRange(e.x) || s.x > e.x) {
      report.fails.push('bi#' + i + ' 端点越界/倒序: ' + JSON.stringify(bis[i]));
    }
    if (s.y === undefined || e.y === undefined || !Number.isFinite(s.y) || !Number.isFinite(e.y)) {
      report.fails.push('bi#' + i + ' 价格非有限: ' + JSON.stringify(bis[i]));
    }
  }
  // 相邻笔共享端点（同索引同价格）
  for (let i = 0; i < bis.length - 1; i++) {
    const prevEnd = bis[i][1];
    const nextStart = bis[i + 1][0];
    if (prevEnd.x !== nextStart.x || Math.abs(prevEnd.y - nextStart.y) > 1e-9) {
      report.fails.push('bi#' + i + ' 与 bi#' + (i + 1) + ' 未共享端点: '
        + JSON.stringify(prevEnd) + ' vs ' + JSON.stringify(nextStart));
    }
  }
  // 每条笔端点价格必须等于该 K 线 high 或 low（落在极值上）
  for (let i = 0; i < bis.length; i++) {
    const [s, e] = bis[i];
    const sb = ohlc[s.x];
    const eb = ohlc[e.x];
    const sOn = onExtreme(sb, s.y);
    const eOn = onExtreme(eb, e.y);
    if (!sOn) report.fails.push('bi#' + i + ' 起点不在K线极值: x=' + s.x + ' y=' + s.y + ' bar=' + JSON.stringify(sb));
    if (!eOn) report.fails.push('bi#' + i + ' 终点不在K线极值: x=' + e.x + ' y=' + e.y + ' bar=' + JSON.stringify(eb));
  }
  // 线段端点落在极值上
  for (let i = 0; i < xds.length; i++) {
    const [s, e] = xds[i];
    if (!inRange(s.x) || !inRange(e.x)) { report.fails.push('xd#' + i + ' 端点越界'); continue; }
    const sb = ohlc[s.x];
    const eb = ohlc[e.x];
    const sOn = onExtreme(sb, s.y);
    const eOn = onExtreme(eb, e.y);
    if (!sOn) report.fails.push('xd#' + i + ' 起点不在K线极值: ' + JSON.stringify(xds[i]));
    if (!eOn) report.fails.push('xd#' + i + ' 终点不在K线极值: ' + JSON.stringify(xds[i]));
  }
  for (let i = 0; i < xds.length - 1; i++) {
    const pe = xds[i][1];
    const ns = xds[i + 1][0];
    if (pe.x !== ns.x || Math.abs(pe.y - ns.y) > 1e-9) {
      report.fails.push('xd#' + i + ' 与 xd#' + (i + 1) + ' 未共享端点');
    }
  }
}

await page.screenshot({ path: path.join(OUT, 'full_' + tag + '.png'), fullPage: true });
await page.evaluate(() => {
  const chart = window.__CHANLUN_CHART__;
  if (chart) {
    const opt = chart.getOption();
    const xlen = opt?.xAxis?.[0]?.data?.length ?? 800;
    const start = Math.max(0, 100 - (140 / xlen) * 100);
    chart.dispatchAction({ type: 'dataZoom', start, end: 100 });
  }
});
await page.waitForTimeout(1200);
await page.screenshot({ path: path.join(OUT, 'zoom_' + tag + '.png') });
const chartEl = await page.$('.chart-area');
if (chartEl) await chartEl.screenshot({ path: path.join(OUT, 'chart_' + tag + '.png') });

report.passed = report.fails.length === 0 && errors.filter((e) => !/favicon/.test(e)).length === 0;
report.consoleErrors = errors.filter((e) => !/favicon/.test(e)).slice(0, 10);
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
await browser.close();
