#!/usr/bin/env python3
"""
Test script to verify Chrome CDP connection.
Run this before the LinkedIn POC to ensure everything is set up correctly.
"""

import asyncio

from playwright.async_api import async_playwright


async def test_cdp_connection():
    """Test if we can connect to Chrome via CDP."""
    try:
        async with async_playwright() as p:
            print("Attempting to connect to Chrome on port 9222...")
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            print("✓ Successfully connected to Chrome!")

            context = browser.contexts[0]
            print(f"✓ Found {len(context.pages)} open page(s)")

            page = context.pages[0] if context.pages else await context.new_page()
            print(f"✓ Current page URL: {page.url}")

            await browser.close()
            print("\n✓ All checks passed! You're ready to run the LinkedIn POC.")
            return True

    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        print("\nMake sure Chrome is running with:")
        print("  google-chrome --remote-debugging-port=9222")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_cdp_connection())
    exit(0 if success else 1)
