// 全市场扫描（P2）浏览器实测：打开 /fundamental → 切到「全市场扫描」→ 运行 → 校验结果表 → 截图
// 用法: node scripts/fundamental-scan-screenshot.mjs [baseUrl] [outDir]
import { chromium } from '/home/skp/workspace/chuma-xian-game/node_modules/playwright/index.mjs';
import fs from 'fs';
import path from 'path';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8010';
const OUT = process.argv[3] ?? '/tmp/fundamental_scan_shots';
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const page = await browser.newPage({ viewport: { width: 1680, height: 2400 } });
const consoleErrors = [], pageErrors = [];
page.on('console', m => { if (m.type()==='error'||m.type()==='warning') consoleErrors.push('['+m.type()+'] '+m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

await page.goto(BASE + '/fundamental', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('.fundamental-view', { timeout: 30000 }).catch(()=>{});

// 切到全市场扫描模式
await page.click('.mode-tabs .mode-tab:nth-child(3)').catch(()=>{});
await page.waitForTimeout(500);

// 设置日期（2026-09-01 之后全部已知财报可用）
await page.fill('input[type="date"]', '2026-09-01').catch(()=>{});
await page.evaluate(() => { const inp = document.querySelector('input[type=date]'); if (inp) inp.dispatchEvent(new Event('input', { bubbles: true })); });
await page.waitForTimeout(300);

// 点击运行按钮
await page.click('button.primary.scan-btn').catch(()=>{});
await page.waitForFunction(() => document.querySelector('.scan-table tbody tr') || document.querySelector('.error-banner') || document.querySelector('.warning-banner'), { timeout: 120000 }).catch(()=>{});
await page.waitForTimeout(2000);

const state = await page.evaluate(() => ({
  modeActive: [...document.querySelectorAll('.mode-tab')].some(b => b.classList.contains('active') && b.textContent.includes('全市场扫描')),
  rows: document.querySelectorAll('.scan-table tbody tr').length,
  stats: [...document.querySelectorAll('.stats-bar .stat-item')].map(s => s.textContent?.trim()),
  firstRow: document.querySelector('.scan-table tbody tr')?.textContent?.trim() ?? '',
  season: document.querySelector('.season-card .season-title')?.textContent?.trim() ?? null,
  error: document.querySelector('.error-banner')?.textContent?.trim() ?? null,
  warning: document.querySelector('.warning-banner')?.textContent?.trim() ?? null,
  tableExists: !!document.querySelector('.scan-table'),
  loadingBtn: document.querySelector('button.primary.scan-btn')?.textContent?.trim() ?? '',
}));
await page.screenshot({ path: path.join(OUT, 'scan_config_result.png'), fullPage: true });

// 展开第一行明细验证
await page.click('.scan-table tbody tr:first-child .score-details summary').catch(()=>{});
await page.waitForTimeout(400);
const detailOpen = await page.evaluate(() => document.querySelectorAll('.scan-table .score-block').length);
await page.screenshot({ path: path.join(OUT, 'scan_detail.png'), fullPage: true });

console.log(JSON.stringify({ state, detailOpen, consoleErrors: consoleErrors.slice(0, 10), pageErrors }, null, 2));
await browser.close();