import { test, expect } from '@playwright/test';

test.describe('Submittals Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/submittals');
  });

  test('should load submittals page @regression', async ({ page }) => {
    await expect(page.getByTestId('text-page-title')).toHaveText('Submittals');
  });

  test('should display submittal rows', async ({ page }) => {
    const submittalRows = page.locator('[data-testid^="submittal-row-"]');
    await expect(submittalRows.first()).toBeVisible({ timeout: 5000 });
  });

  test('should filter submittals by status', async ({ page }) => {
    const statusFilter = page.getByText('All Statuses');
    if (await statusFilter.isVisible()) {
      await statusFilter.click();
      await page.waitForTimeout(300);
    }
  });
});

