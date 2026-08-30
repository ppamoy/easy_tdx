// V91 新浪补充浏览器实测：扫描配置填新浪自选池 → 运行 → 数据源列出现「新浪」徽章
import { chromium } from '/home/skp/workspace/chuma-xian-game/node_modules/playwright/index.mjs';
import fs from 'fs';
import path from 'path';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8000';
const OUT = '/tmp/v91_shots';
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const page = await browser.newPage({ viewport: { width: 1680, height: 2200 } });
const consoleErrors = [], pageErrors = [];
page.on('console', m => { if (m.type()==='error'||m.type()==='warning') consoleErrors.push('['+m.type()+'] '+m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

await page.goto(BASE + '/fundamental', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('.fundamental-view', { timeout: 30000 }).catch(()=>{});

// 切全市场扫描模式
await page.click('.mode-tabs .mode-tab:nth-child(3)').catch(()=>{});
await page.waitForTimeout(500);

// 历史日期（gpcw 未覆盖的 2019）
await page.fill('input[type="date"]', '2019-11-15');
await page.evaluate(() => { const inp = document.querySelector('input[type=date]'); if (inp) inp.dispatchEvent(new Event('input', { bubbles: true })); });
await page.waitForTimeout(300);

// 新浪补充自选池
const ta = await page.$('.sina-pool-group textarea');
if (ta) {
  await ta.fill('600519\n000858\n300750');
}
await page.waitForTimeout(300);

await page.click('.config-bar button.primary.scan-btn').catch(()=>{});
await page.waitForFunction(() => document.querySelector('.scan-table tbody tr') || document.querySelector('.error-banner') || document.querySelector('.warning-banner'), { timeout: 120000 }).catch(()=>{});
await page.waitForTimeout(2500);

const state = await page.evaluate(() => ({
  rows: document.querySelectorAll('.scan-table tbody tr').length,
  sinaBadges: [...document.querySelectorAll('.ds-badge.sina')].length,
  gpcwBadges: [...document.querySelectorAll('.ds-badge.gpcw')].length,
  firstRow: document.querySelector('.scan-table tbody tr')?.textContent?.trim() ?? '',
  configHasSinaInput: !!document.querySelector('.sina-pool-group textarea'),
  error: document.querySelector('.error-banner')?.textContent?.trim() ?? null,
}));
await page.screenshot({ path: path.join(OUT, 'v91_sina_fallback.png'), fullPage: true });

console.log(JSON.stringify({ state, consoleErrors: consoleErrors.slice(0,10), pageErrors }, null, 2));
await browser.close();