#!/usr/bin/env node
// E2E test: verify HybridView page renders and API works
// Per AGENTS.md §1: assert real behavior (network request + rendered content), not just DOM existence

const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  const results = [];
  const log = (name, pass, detail) => results.push({ name, pass, detail });

  // Track network requests
  const apiCalls = [];
  page.on('request', req => {
    if (req.url().includes('/api/v1/hybrid')) {
      apiCalls.push({ url: req.url(), method: req.method() });
    }
  });
  page.on('response', async resp => {
    if (resp.url().includes('/api/v1/hybrid')) {
      const idx = apiCalls.findIndex(c => c.url === resp.url());
      if (idx >= 0) apiCalls[idx].status = resp.status();
    }
  });

  try {
    // 1. Navigate to hybrid page
    await page.goto('http://127.0.0.1:8001/hybrid', { waitUntil: 'networkidle', timeout: 15000 });
    log('navigate', true, 'page loaded');

    // 2. Check title
    const title = await page.title();
    log('title', title.includes('easy'), `title="${title}"`);

    // 3. Check nav link exists and is active
    const navLink = await page.$('a[href="/hybrid"]');
    log('nav-link', !!navLink, '吴伟志+缠论 nav link present');

    // 4. Check page heading
    const heading = await page.textContent('h2');
    log('heading', heading && heading.includes('吴伟志'), `h2="${heading}"`);

    // 5. Check season card loaded (API call to /hybrid/season)
    await page.waitForTimeout(2000); // wait for season API call
    const seasonCall = apiCalls.find(c => c.url.includes('/hybrid/season'));
    log('season-api', seasonCall && seasonCall.status === 200,
      `season API: ${seasonCall ? seasonCall.status : 'not called'}`);

    // 6. Check form inputs
    const codeInput = await page.$('input[placeholder="600000"]');
    log('code-input', !!codeInput, 'stock code input present');

    const periodSelect = await page.$('select');
    log('period-select', !!periodSelect, 'period select present');

    // 7. Check analyze button
    const btn = await page.$('button.btn-run');
    log('analyze-btn', !!btn, 'analyze button present');

    // 8. Fill form and click analyze (real behavior test)
    if (codeInput) {
      await codeInput.fill('600000');
    }

    // Click the analyze button
    if (btn) {
      await btn.click();
      // Wait for API call and result
      await page.waitForTimeout(8000);

      // Check if analyze API was called
      const analyzeCall = apiCalls.find(c => c.url.includes('/hybrid/analyze'));
      log('analyze-api', analyzeCall && analyzeCall.status === 200,
        `analyze API: ${analyzeCall ? analyzeCall.status : 'not called'}`);

      // Check if result rendered
      const finalSignal = await page.$('.final-signal');
      log('result-rendered', !!finalSignal, 'final signal card rendered');

      // Check arch layers
      const archLayers = await page.$$('.arch-layer');
      log('arch-layers', archLayers.length === 3, `${archLayers.length} architecture layers`);

      // Check signals table
      const signalsRows = await page.$$('.signals-table tbody tr');
      log('signals-table', signalsRows.length > 0, `${signalsRows.length} signal rows`);
    }

    // 9. Take screenshot
    await page.screenshot({ path: '/tmp/hybrid_page.png', fullPage: true });
    log('screenshot', true, 'saved to /tmp/hybrid_page.png');

  } catch (err) {
    log('error', false, err.message);
  } finally {
    await context.close();
  }

  // Print results
  console.log('\n=== E2E Test Results ===');
  let passed = 0, failed = 0;
  for (const r of results) {
    const icon = r.pass ? '✅' : '❌';
    console.log(`${icon} ${r.name}: ${r.detail}`);
    if (r.pass) passed++; else failed++;
  }
  console.log(`\n${passed}/${results.length} passed`);
  process.exit(failed > 0 ? 1 : 0);
})();
