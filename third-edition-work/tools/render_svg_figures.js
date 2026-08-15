const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const root = path.resolve(process.argv[2]);
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });
  const pages = [];
  for (const chapter of ['ch03', 'ch4', 'ch5', 'ch6', 'ch7', 'ch8']) {
    const directory = path.join(root, chapter);
    if (!fs.existsSync(directory)) continue;
    for (const name of fs.readdirSync(directory).filter((item) => item.endsWith('.svg'))) {
      const page = await browser.newPage({ viewport: { width: 2400, height: 1350 }, deviceScaleFactor: 1 });
      await page.goto('file:///' + path.join(directory, name).replace(/\\/g, '/'));
      await page.screenshot({ path: path.join(directory, name.replace(/\.svg$/, '.png')) });
      pages.push(path.join(chapter, name));
      await page.close();
    }
  }
  await browser.close();
  console.log(`rendered ${pages.length} figures`);
})();
