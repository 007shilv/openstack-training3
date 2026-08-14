const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

async function main() {
  const manifestPath = path.resolve(process.argv[2]);
  const chromePath = process.argv[3] || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const revisionRoot = path.dirname(path.dirname(manifestPath));
  const records = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const browser = await chromium.launch({ executablePath: chromePath, headless: true });

  try {
    for (const record of records) {
      const svgPath = path.join(revisionRoot, record.svg);
      const pngPath = path.join(revisionRoot, record.png);
      const svg = fs.readFileSync(svgPath, 'utf8');
      const match = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
      if (!match) throw new Error(`missing fixed viewBox: ${svgPath}`);
      const width = Number(match[1]);
      const height = Number(match[2]);
      const context = await browser.newContext({
        viewport: { width, height },
        deviceScaleFactor: 2,
      });
      const page = await context.newPage();
      await page.goto(pathToFileURL(svgPath).href, { waitUntil: 'load' });
      await page.screenshot({
        path: pngPath,
        type: 'png',
        clip: { x: 0, y: 0, width, height },
        animations: 'disabled',
      });
      await context.close();
      process.stdout.write(`rendered ${record.number} ${width * 2}x${height * 2}\n`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
