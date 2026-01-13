import { Page } from '@playwright/test';

/**
 * Helper function to wait for the app to be fully loaded
 */
export async function waitForAppLoad(page: Page) {
  // Wait for the main content to be visible
  await page.waitForSelector('[data-testid="text-page-title"]', { timeout: 10000 });
}

/**
 * Helper function to navigate to a page via sidebar
 */
export async function navigateToPage(page: Page, pageName: string) {
  await page.getByTestId(`nav-${pageName.toLowerCase()}`).click();
  await page.waitForURL(`/${pageName.toLowerCase()}`);
}

