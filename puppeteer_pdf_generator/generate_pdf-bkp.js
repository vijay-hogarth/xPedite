const puppeteer = require('puppeteer');
const fs = require('fs');

async function generatePdf() {
let browser;
try {
    // Read the JSON arguments passed from the Python script
    const args = JSON.parse(process.argv[2]);
    const htmlContent = args.htmlContent;
    const outputPath = args.outputPath;
    const deviceWidth = parseInt(args.deviceWidth);

    browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();

    // Set the viewport to the desired device width
    await page.setViewport({
        width: deviceWidth, 
        height: 1080, // A temporary height, will be overridden
        deviceScaleFactor: 1,
    });

    // Load the HTML content
    await page.setContent(htmlContent, {
        waitUntil: 'networkidle0'
    });

    // Wait for all fonts to be loaded and ready for accurate measurement
    await page.evaluate(() => document.fonts.ready);

    // Inject CSS to force the main container to be full-width
    await page.addStyleTag({
        content: `
            html, body { margin: 0 !important; padding: 0 !important; }
            body > * {
                width: 100% !important;
                max-width: 100% !important;
                margin: 0 !important;
                box-sizing: border-box !important;
            }
        `
    });

    // Calculate the final height *inside this browser instance*
    // const pdfHeight = await page.evaluate(() => {
    //     const footer = document.querySelector('.footer');
    //     if (footer) {
    //         footer.style.position = 'static';
    //     }
    //     // Use the most reliable property for the full rendered height
    //     return document.documentElement.scrollHeight;
    // });

    const bodyHeight = await page.evaluate(() => {
        return Math.max(
            document.body.scrollHeight,
            document.body.offsetHeight,
            document.documentElement.scrollHeight,
            document.documentElement.offsetHeight
        );
    });

    // Generate the PDF using the self-calculated dimensions
    // await page.pdf({
    //     path: outputPath,
    //     width: `${deviceWidth}px`,
    //     height: `${pdfHeight}px`,
    //     printBackground: true,
    //     margin: { top: '0px', right: '0px', bottom: '0px', left: '0px' },
    //     preferCSSPageSize: false // CRUCIAL: Ignore any conflicting @page CSS
    // });

    await page.pdf({
        path: outputPath,
        width: `${deviceWidth}px`,
        height: `${bodyHeight}px`,   // <-- measured height only once
        printBackground: true,
        margin: { top: '0px', right: '0px', bottom: '0px', left: '0px' }
    });

    console.log(`PDF generated successfully at ${outputPath}`);
    process.exit(0);

} catch (error) {
    console.error('Error generating PDF with Puppeteer:', error);
    process.exit(1);
} finally {
    if (browser) {
        await browser.close();
    }
}
}

generatePdf();