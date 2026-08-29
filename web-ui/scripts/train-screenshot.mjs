// 缠论学习训练页浏览器测试（P0）：逐步揭示训练 + 复盘讲解。
// 用法: node scripts/train-screenshot.mjs [code] [category] [count] [baseUrl]
import { chromium } from '/home/skp/workspace/chuma-xian-game/node_modules/playwright/index.mjs';
import fs from 'fs';
import path from 'path';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:3012';
const [, , codeArg, categoryArg, countArg, outDirArg] = process.argv;
const CODE = codeArg ?? '000001';
const CATEGORY = categoryArg ?? 'DAY';
const COUNT = countArg ?? '400';
const OUT = outDirArg ?? '/tmp/train_shots';
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const page = await browser.newPage({ viewport: { width: 1680, height: 2400 } });
const consoleErrors = [], pageErrors = [];
page.on('console', m => { if (m.type()==='error'||m.type()==='warning') consoleErrors.push('['+m.type()+'] '+m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

await page.goto(BASE + '/train', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('.train-view', { timeout: 30000 }).catch(()=>{});
await page.fill('.config-bar input[type="text"]', CODE).catch(()=>{});
await page.selectOption('.config-bar select', CATEGORY).catch(()=>{});
await page.fill('.config-bar input[type="number"]', COUNT).catch(()=>{});
await page.click('.primary').catch(()=>{});
await page.waitForFunction(() => document.querySelector('.question-card') || document.querySelector('.error-banner') || document.querySelector('.review-panel'), { timeout: 150000 }).catch(()=>{});
await page.waitForTimeout(1500);

// 训练模式跑 6 轮作答
const rounds = [];
for (let i = 0; i < 6; i++) {
  const q = await page.$('.q-actions .choice');
  if (!q) break;
  const choice = ['buy','sell','hold'][i % 3];
  await page.click('.q-actions .choice.' + choice).catch(()=>{});
  await page.waitForTimeout(400);
  const r = await page.evaluate(() => ({
    q: document.querySelector('.q-text')?.textContent?.trim() ?? '',
    answers: [...document.querySelectorAll('.answer-line')].map(l => l.textContent?.trim()),
    outcome: !!document.querySelector('.outcome-box'),
    score: [...document.querySelectorAll('.score-item b')].map(b => b.textContent),
  }));
  rounds.push(r);
  const next = await page.$('.next-btn');
  if (!next) break;
  await page.click('.next-btn');
  await page.waitForTimeout(500);
}
await page.screenshot({ path: path.join(OUT, 'train_flow.png'), fullPage: true });

// 复盘模式
await page.click('.mode-tabs .tab:nth-child(2)').catch(()=>{});
await page.waitForTimeout(1000);
const review = await page.evaluate(() => ({
  rows: document.querySelectorAll('.review-panel tbody tr').length,
  firstRow: document.querySelector('.review-panel tbody tr')?.textContent?.trim() ?? '',
}));
await page.screenshot({ path: path.join(OUT, 'train_review.png'), fullPage: true });

console.log(JSON.stringify({ rounds, review, consoleErrors: consoleErrors.slice(0,10), pageErrors }, null, 2));
await browser.close();
