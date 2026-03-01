import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const htmlPath = path.join(__dirname, 'demo.html');
const videoDir = path.join(__dirname);

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1200, height: 720 },
    recordVideo: { dir: videoDir, size: { width: 1200, height: 720 } },
  });
  const page = await context.newPage();

  await page.goto(`file://${htmlPath}`);

  // Wait for the demo to finish (scenes take ~25s total)
  await page.waitForTimeout(28000);

  await context.close();
  await browser.close();

  console.log('Recording saved to', videoDir);
}

main().catch(e => { console.error(e); process.exit(1); });
