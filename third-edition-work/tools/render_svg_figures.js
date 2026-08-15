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
  for (const chapter of ['ch01', 'ch02', 'ch03', 'ch4', 'ch5', 'ch6', 'ch7', 'ch8', 'ch9', 'ch10', 'ch11', 'ch12', 'ch13']) {
    const directory = path.join(root, chapter);
    if (!fs.existsSync(directory)) continue;
    for (const name of fs.readdirSync(directory).filter((item) => item.endsWith('.svg'))) {
      const page = await browser.newPage({ viewport: { width: 2400, height: 1500 }, deviceScaleFactor: 1 });
      const svg = fs.readFileSync(path.join(directory, name), 'utf8');
      await page.setContent(`<!doctype html><html><head><style>
        html, body { margin: 0; width: 2400px; height: 1500px; overflow: hidden; background: white; }
        svg { display: block; width: 2400px !important; height: 1500px !important; }
      </style></head><body>${svg}</body></html>`);
      await page.screenshot({ path: path.join(directory, name.replace(/\.svg$/, '.png')) });
      pages.push(path.join(chapter, name));
      await page.close();
    }
  }
  await browser.close();
  console.log(`rendered ${pages.length} figures`);
})();
