// Use puppeteer-core instead of puppeteer
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const os = require('os');
const path = require('path');

// Helper function to find the default path for Chrome
function getChromeExecutablePath() {
    if (os.platform() === 'win32') {
        // Look for Chrome on Windows in common locations
        const programFiles = process.env['ProgramFiles(x86)'] || process.env.ProgramFiles;
        const chromePath = path.join(programFiles, 'Google', 'Chrome', 'Application', 'chrome.exe');
        if (fs.existsSync(chromePath)) {
            return chromePath;
        }
    } else if (os.platform() === 'darwin') {
        // Standard path for Chrome on macOS
        const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
        if (fs.existsSync(chromePath)) {
            return chromePath;
        }
    }
    // Fallback if Chrome is not found in default locations
    console.error('❌ Error: Google Chrome could not be found in its default location.');
    process.exit(1);
}


async function generateExactPdf() {
    const args = JSON.parse(process.argv[2]);
    const htmlPath = args.htmlPath;
    const outputPath = args.outputPath;
    const deviceWidth = args.deviceWidth || 610;
    const viewType = args.viewType || 'desktop';

    if (!htmlPath || !fs.existsSync(htmlPath)) {
        console.error('❌ Error: HTML input file path is missing or does not exist.');
        process.exit(1);
    }
    const htmlContent = fs.readFileSync(htmlPath, 'utf8');

    let browser;
    try {
        // Get the path to the user's installed Chrome
        const executablePath = getChromeExecutablePath();

        // Launch Puppeteer using the found Chrome executable
        browser = await puppeteer.launch({
            executablePath, // <-- THIS IS THE IMPORTANT NEW PART
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        });

        // ... (the rest of your code is exactly the same) ...

        const page = await browser.newPage();
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
        
        await page.setViewport({
            width: viewportWidth,
            height: 800,
            deviceScaleFactor: deviceScaleFactor,
            isMobile: (viewType === 'mobile')
        });

        let finalHtmlContent = htmlContent;
        if (!finalHtmlContent.includes('<html')) {
            finalHtmlContent = `<!DOCTYPE html><html><head></head><body>${finalHtmlContent}</body></html>`;
        }
        if (!finalHtmlContent.includes('<head>')) {
            finalHtmlContent = finalHtmlContent.replace('<body>', '<head></head><body>');
        }
        
        const metaViewportTag = `<meta name="viewport" content="width=device-width, initial-scale=1.0, shrink-to-fit=no">`;
        if (!finalHtmlContent.includes('<meta name="viewport"')) {
            const headEndIndex = finalHtmlContent.indexOf('</head>');
            if (headEndIndex !== -1) {
                finalHtmlContent = finalHtmlContent.substring(0, headEndIndex) +
                    metaViewportTag +
                    finalHtmlContent.substring(headEndIndex);
            }
        }
        
        const htmlTitleContent = pdfTitle.replace(' PDF', '');
        if (!finalHtmlContent.includes('<title>')) {
            const headStartTagIndex = finalHtmlContent.indexOf('<head>');
            if (headStartTagIndex !== -1) {
                finalHtmlContent = finalHtmlContent.substring(0, headStartTagIndex + '<head>'.length) +
                    `<title>${htmlTitleContent}</title>` +
                    finalHtmlContent.substring(headStartTagIndex + '<head>'.length);
            }
        }
        
        await page.setContent(finalHtmlContent, { waitUntil: 'networkidle0' });
        await page.emulateMediaType('screen');
        
        await page.waitForFunction(() => {
            const images = Array.from(document.querySelectorAll('img'));
            return images.every(img => img.complete || img.naturalWidth === 0);
        }, { timeout: 10000 }).catch(() => console.log('Some images might not have loaded within timeout.'));
        await page.evaluateHandle('document.fonts.ready');
        await new Promise(resolve => setTimeout(resolve, 500));
        
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
        
        await page.setViewport({
            width: viewportWidth,
            height: contentHeight,
            deviceScaleFactor: deviceScaleFactor,
            isMobile: (viewType === 'mobile')
        });
        
        const pdfWidthInches = viewportWidth / 96;
        const pdfHeightInches = contentHeight / 96;
        
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
