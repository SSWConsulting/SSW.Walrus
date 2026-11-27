// Usage: node scripts/shoot-dashboard.js <index.html> <out-dir> [--text]
// Clicks every sidebar nav item (chapters, then People) and saves a 1920x1080
// first-screen shot and a full-page shot of each. With --text it also saves the
// visible text of each view (<slug>.txt) so the shots can be checked for names
// or client info that shouldn't be published.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const [html, outDir, flag] = process.argv.slice(2);
  if (!html || !outDir) {
    console.error('usage: node scripts/shoot-dashboard.js <index.html> <out-dir> [--text]');
    process.exit(2);
  }
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto('file://' + path.resolve(html));
  await page.waitForTimeout(2500);
  const items = page.locator('aside .ds-navitem:visible');
  const n = await items.count();
  for (let i = 0; i < n; i++) {
    const item = items.nth(i);
    const label = (await item.innerText()).trim().replace(/\s+/g, ' ');
    const slug = `${String(i + 1).padStart(2, '0')}-${label.toLowerCase().replace(/^\d+\s*/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`;
    await item.click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(outDir, `${slug}.png`) });
    await page.screenshot({ path: path.join(outDir, `${slug}-full.png`), fullPage: true });
    if (flag === '--text') {
      fs.writeFileSync(path.join(outDir, `${slug}.txt`), await page.locator('body').innerText());
    }
    console.log('shot', slug);
  }
  await browser.close();
})();
