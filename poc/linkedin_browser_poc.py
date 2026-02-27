"""
LinkedIn Browser Control POC

Connects to a running Chrome instance via CDP to post content to LinkedIn.
Requires Chrome to be launched with: google-chrome --remote-debugging-port=9222

Usage:
    python poc/linkedin_browser_poc.py "Your post content here"
"""

import asyncio
import sys

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


async def post_to_linkedin(content: str) -> bool:
    """
    Post content to LinkedIn using an existing Chrome session.

    Args:
        content: The text content to post

    Returns:
        True if successful, False otherwise
    """
    try:
        async with async_playwright() as p:
            print("Connecting to Chrome on port 9222...")
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")

            # Use existing context (logged-in session)
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()

            print("Navigating to LinkedIn feed...")
            await page.goto("https://www.linkedin.com/feed/", wait_until="networkidle")

            # Wait for and click "Start a post" button
            print("Clicking 'Start a post' button...")
            await page.click('button[aria-label*="Start a post"]', timeout=10000)

            # Wait for editor to appear and fill content
            print("Filling post content...")
            await page.wait_for_selector('.ql-editor[contenteditable="true"]', timeout=5000)
            await page.fill('.ql-editor[contenteditable="true"]', content)

            # Click Post button
            print("Clicking 'Post' button...")
            await page.click('button[aria-label*="Post"]', timeout=5000)

            # Wait a moment for the post to be submitted
            await asyncio.sleep(2)

            print("✓ Post submitted successfully!")
            await browser.close()
            return True

    except PlaywrightTimeoutError as e:
        print(f"✗ Timeout error: {e}")
        print("Make sure you're logged into LinkedIn in the Chrome browser.")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def main():
    if len(sys.argv) < 2:
        print("Usage: python poc/linkedin_browser_poc.py 'Your post content'")
        print("\nMake sure Chrome is running with:")
        print("  google-chrome --remote-debugging-port=9222")
        sys.exit(1)

    content = sys.argv[1]
    success = await post_to_linkedin(content)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
