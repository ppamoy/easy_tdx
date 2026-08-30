// 训练排行榜（V90）浏览器实测：打开 /train → 切到「🏆 排行榜」→ 校验表格 + 截图
// 用法: node scripts/train-leaderboard-screenshot.mjs [baseUrl]
import { chromium } from '/home/skp/workspace/chuma-xian-game/node_modules/playwright/index.mjs';
import fs from 'fs';
import path from 'path';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8000';
const OUT = process.env.OUT_DIR ?? '/tmp/train_lb_shots';
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const page = await browser.newPage({ viewport: { width: 1680, height: 1400 } });
const consoleErrors = [], pageErrors = [];
page.on('console', m => { if (m.type()==='error'||m.type()==='warning') consoleErrors.push('['+m.type()+'] '+m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

await page.goto(BASE + '/train', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('.train-view', { timeout: 30000 }).catch(()=>{});
await page.waitForTimeout(2000);

// 切到排行榜 tab（排行榜是最后一个 tab）
const tabTexts = await page.$$eval('.mode-tabs .tab', ts => ts.map(t => t.textContent));
const lbIdx = tabTexts.findIndex(t => t.includes('排行榜'));
if (lbIdx >= 0) await page.click('.mode-tabs .tab:nth-child(' + (lbIdx + 1) + ')');
else await page.click('.mode-tabs .tab:last-child').catch(()=>{});
await page.waitForSelector('.leaderboard-panel', { timeout: 30000 }).catch(()=>{});
await page.waitForTimeout(1500);

const state = await page.evaluate(() => ({
  panel: !!document.querySelector('.leaderboard-panel'),
  rows: document.querySelectorAll('.lb-table tbody tr').length,
  firstRow: document.querySelector('.lb-table tbody tr')?.textContent?.trim() ?? '',
  emptyMsg: document.querySelector('.lb-empty')?.textContent ?? '',
  errors: document.querySelector('.error-banner')?.textContent ?? null,
}));
await page.screenshot({ path: path.join(OUT, 'train_leaderboard.png'), fullPage: true });

console.log(JSON.stringify({ state, consoleErrors: consoleErrors.slice(0, 10), pageErrors }, null, 2));
await browser.close();