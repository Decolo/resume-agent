/**
 * LinkedIn Browser Control POC (TypeScript)
 *
 * Connects to a running Chrome instance via CDP to post content to LinkedIn.
 * Requires Chrome to be launched with: google-chrome --remote-debugging-port=9222
 *
 * Usage:
 *   npx ts-node poc/linkedin_browser_poc.ts
 */

import puppeteer from 'puppeteer-core';

async function postToLinkedIn(content: string): Promise<boolean> {
  try {
    console.log('Connecting to Chrome on port 9222...');
    const browser = await puppeteer.connect({
      browserURL: 'http://localhost:9222',
    });

    const pages = await browser.pages();
    const page = pages[0] || (await browser.newPage());

    console.log('Navigating to LinkedIn feed...');
    await page.goto('https://www.linkedin.com/feed/', {
      waitUntil: 'networkidle2',
    });

    // Wait for and click "Start a post" button
    console.log('Clicking "Start a post" button...');
    await page.waitForSelector('button[aria-label*="Start a post"]', {
      timeout: 10000,
    });
    await page.click('button[aria-label*="Start a post"]');

    // Wait for editor to appear and fill content
    console.log('Filling post content...');
    await page.waitForSelector('.ql-editor[contenteditable="true"]', {
      timeout: 5000,
    });
    await page.type('.ql-editor[contenteditable="true"]', content);

    // Click Post button
    console.log('Clicking "Post" button...');
    await page.click('button[aria-label*="Post"]');

    // Wait a moment for the post to be submitted
    await new Promise((resolve) => setTimeout(resolve, 2000));

    console.log('✓ Post submitted successfully!');
    await browser.disconnect();
    return true;
  } catch (error) {
    console.error('✗ Error:', error);
    console.log('Make sure you\'re logged into LinkedIn in the Chrome browser.');
    return false;
  }
}

// Main execution
const content = process.argv[2] || 'Test post from LinkedIn Browser POC';
postToLinkedIn(content).then((success) => {
  process.exit(success ? 0 : 1);
});
