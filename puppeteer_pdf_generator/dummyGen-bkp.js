const puppeteer = require('puppeteer');
const fs = require('fs');

async function generateExactPdf() {
// Parse arguments passed from Python or CLI
const args = JSON.parse(process.argv[2]);
const htmlContent = args.htmlContent;
const outputPath = args.outputPath;
const deviceWidth = args.deviceWidth || 610; // default width if not provided
const viewType = args.viewType || 'desktop'; // 'mobile' or 'desktop'

let browser;
try {
    browser = await puppeteer.launch({
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage'
        ]
    });

    const page = await browser.newPage();

    // Determine viewport width
    const defaultDesktopWidth = 600;
    const mobileWidth = 360;
    let viewportWidth;
    let pdfTitle;
    let deviceScaleFactor = 2;

    if (viewType === 'mobile') {
        viewportWidth = mobileWidth;
        pdfTitle = 'Mobile View PDF';
    } else if (deviceWidth !== defaultDesktopWidth) {
        viewportWidth = parseInt(deviceWidth, 10);
        pdfTitle = 'Custom View PDF';
    } else {
        viewportWidth = defaultDesktopWidth;
        pdfTitle = 'Desktop View PDF';
    }

    // Set initial viewport
    await page.setViewport({
        width: viewportWidth,
        height: 800,
        deviceScaleFactor: deviceScaleFactor,
        isMobile: (viewType === 'mobile')
    });

    // Ensure HTML is complete
    let finalHtmlContent = htmlContent;
    if (!finalHtmlContent.includes('<html')) {
        finalHtmlContent = `<!DOCTYPE html><html><head></head><body>${finalHtmlContent}</body></html>`;
    }
    if (!finalHtmlContent.includes('<head>')) {
        finalHtmlContent = finalHtmlContent.replace('<body>', '<head></head><body>');
    }

    // Add meta viewport for mobile scaling
    const metaViewportTag = `<meta name="viewport" content="width=device-width, initial-scale=1.0, shrink-to-fit=no">`;
    if (!finalHtmlContent.includes('<meta name="viewport"')) {
        const headEndIndex = finalHtmlContent.indexOf('</head>');
        if (headEndIndex !== -1) {
            finalHtmlContent = finalHtmlContent.substring(0, headEndIndex) +
                metaViewportTag +
                finalHtmlContent.substring(headEndIndex);
        }
    }

    // Add title if missing
    const htmlTitleContent = pdfTitle.replace(' PDF', '');
    if (!finalHtmlContent.includes('<title>')) {
        const headStartTagIndex = finalHtmlContent.indexOf('<head>');
        if (headStartTagIndex !== -1) {
            finalHtmlContent = finalHtmlContent.substring(0, headStartTagIndex + '<head>'.length) +
                `<title>${htmlTitleContent}</title>` +
                finalHtmlContent.substring(headStartTagIndex + '<head>'.length);
        }
    }

    // Load HTML into Puppeteer
    await page.setContent(finalHtmlContent, { waitUntil: 'networkidle0' });
    await page.emulateMediaType('screen');

    // Wait for images and fonts
    await page.waitForFunction(() => {
        const images = Array.from(document.querySelectorAll('img'));
        return images.every(img => img.complete || img.naturalWidth === 0);
    }, { timeout: 10000 }).catch(() => console.log('Some images might not have loaded within timeout.'));
    await page.evaluateHandle('document.fonts.ready');
    await new Promise(resolve => setTimeout(resolve, 500));

    // Measure exact content height
    const contentHeight = await page.evaluate(() => {
        let lastVisibleElement = null;
        let maxBottom = 0;
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
            const rect = el.getBoundingClientRect();
            const hasVisibleContent = el.textContent.trim().length > 0 ||
                (el.tagName === 'IMG' && el.complete) ||
                (style.backgroundImage && style.backgroundImage !== 'none');
            if (hasVisibleContent && rect.bottom > maxBottom) {
                maxBottom = rect.bottom;
                lastVisibleElement = el;
            }
        }
        if (lastVisibleElement) {
            const style = window.getComputedStyle(lastVisibleElement);
            const marginBottom = parseInt(style.marginBottom, 10) || 0;
            return Math.ceil(maxBottom + marginBottom);
        }
        return Math.ceil(document.body.getBoundingClientRect().bottom);
    });

    // Adjust viewport to match content height
    await page.setViewport({
        width: viewportWidth,
        height: contentHeight,
        deviceScaleFactor: deviceScaleFactor,
        isMobile: (viewType === 'mobile')
    });

    // Convert px → inches for PDF size
    const pdfWidthInches = viewportWidth / 96;
    const pdfHeightInches = contentHeight / 96;

    // Generate PDF
    await page.pdf({
        path: outputPath,
        printBackground: true,
        width: `${pdfWidthInches}in`,
        height: `${pdfHeightInches}in`,
        margin: { top: '0', right: '0', bottom: '0', left: '0' },
        pageRanges: '1',
        preferCSSPageSize: true,
        displayHeaderFooter: false
    });

    console.log(`✅ PDF generated successfully at ${outputPath}`);
    process.exit(0);

} catch (error) {
    console.error('❌ Error generating PDF:', error);
    process.exit(1);
} finally {
    if (browser) {
        await browser.close();
    }
}
}

generateExactPdf();