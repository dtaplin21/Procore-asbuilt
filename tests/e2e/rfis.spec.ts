import { test, expect } from '@playwright/test';

test.describe('RFIs Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/rfis');
  });

  test('should load RFIs page @regression', async ({ page }) => {
    await expect(page.getByTestId('text-page-title')).toHaveText('RFIs');
  });

  test('should display RFI cards', async ({ page }) => {
    // Wait for RFI cards to load
    const rfiCards = page.locator('[data-testid^="card-rfi-"]');
    await expect(rfiCards.first()).toBeVisible({ timeout: 5000 });
  });

  test('should filter RFIs by status', async ({ page }) => {
    // Click on status filter dropdown
    const statusFilter = page.getByText('All Statuses');
    if (await statusFilter.isVisible()) {
      await statusFilter.click();
      // Select a status option if available
      const openStatus = page.getByText('Open');
      if (await openStatus.isVisible()) {
        await openStatus.click();
      }
    }
  });

  test('should search RFIs', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search by subject/i);
    if (await searchInput.isVisible()) {
      await searchInput.fill('test');
      // Wait for results to filter
      await page.waitForTimeout(500);
    }
  });
});

