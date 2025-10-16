const puppeteer = require('puppeteer');
const fs = require('fs');

async function generateExactPdf() {
    const args = JSON.parse(process.argv[2]);
    const htmlContent = args.htmlContent;
    const outputPath = args.outputPath;
    const deviceWidth = parseInt(args.deviceWidth); // e.g. 357

    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();

    // Step 1: Set mobile viewport
    await page.setViewport({
        width: deviceWidth,
        height: 800,
        deviceScaleFactor: 1,
        isMobile: true
    });

    // Step 2: Load HTML
    await page.setContent(htmlContent, { waitUntil: 'networkidle0' });
    await page.evaluate(() => document.fonts.ready);

    // Step 3: Measure content height in px
    const contentHeightPx = await page.evaluate(() => {
        const body = document.body;
        const html = document.documentElement;
        return Math.max(
            body.scrollHeight, body.offsetHeight,
            html.clientHeight, html.scrollHeight, html.offsetHeight
        );
    });

    // Step 4: Convert px → inches (Chromium expects inches for @page size)
    const pxToInch = px => px / 96; // 96px = 1in
    const pageWidthIn = pxToInch(deviceWidth);
    const pageHeightIn = pxToInch(contentHeightPx);

    // Step 5: Inject CSS to force exact PDF page size
    await page.addStyleTag({
        content: `
            @page {
                size: ${pageWidthIn}in ${pageHeightIn}in;
                margin: 0;
            }
            html, body {
                margin: 0 !important;
                padding: 0 !important;
                width: ${deviceWidth}px !important;
                height: ${contentHeightPx}px !important;
                overflow: hidden !important;
            }
        `
    });

    // Step 6: Generate PDF with CSS page size
    await page.pdf({
        path: outputPath,
        printBackground: true,
        preferCSSPageSize: true,
        margin: { top: 0, right: 0, bottom: 0, left: 0 }
    });

    await browser.close();
    console.log(`✅ Exact-size PDF generated at ${outputPath}`);
}

generateExactPdf();