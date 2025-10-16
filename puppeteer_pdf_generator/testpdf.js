const puppeteer = require('puppeteer');
const fs = require('fs');

async function generatePdf() {
  let browser;
  try {
    const args = JSON.parse(process.argv[2]);
    const htmlContent = args.htmlContent;
    const outputPath = args.outputPath;

    const pdfWidth = 375; // Mobile view width

    browser = await puppeteer.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();
    await page.setViewport({ width: pdfWidth, height: 1080, deviceScaleFactor: 1 });

    // Load HTML
    await page.setContent(htmlContent, { waitUntil: 'networkidle0' });
    await page.evaluate(() => document.fonts.ready);

    // Force correct layout for email templates
    await page.addStyleTag({
      content: `
        html, body {
          margin: 0 !important;
          padding: 0 !important;
          min-height: auto !important;
          height: auto !important;
        }
        body {
          display: flex;
          justify-content: center;
        }
        body > * {
          max-width: 600px;
          width: 100% !important;
          box-sizing: border-box !important;
        }
      `
    });

    // Measure final height (last element bottom)
    const pdfHeight = await page.evaluate(() => {
      const body = document.body;
      const html = document.documentElement;
      const lastEl = body.lastElementChild || body;
      const rect = lastEl.getBoundingClientRect();
      const bottom = rect.bottom + window.scrollY;

      return Math.ceil(
        Math.max(
          body.scrollHeight,
          body.offsetHeight,
          html.clientHeight,
          html.scrollHeight,
          html.offsetHeight,
          bottom
        )
      );
    });

    // Export as single tall page
    await page.pdf({
      path: outputPath,
      width: `${pdfWidth}px`,
      height: `${pdfHeight}px`,
      printBackground: true,
      margin: { top: '0px', right: '0px', bottom: '0px', left: '0px' }
    });

    console.log(`✅ Mobile single-page PDF generated at ${outputPath}`);
    process.exit(0);

  } catch (error) {
    console.error('❌ Puppeteer error:', error);
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
}

generatePdf();
