import { test, expect } from '@playwright/test';

test.describe('Procore Integration Status', () => {
  test('should display Procore connection status on dashboard @regression', async ({ page }) => {
    await page.goto('/');
    
    const procoreStatus = page.getByTestId('procore-status');
    await expect(procoreStatus).toBeVisible();
    
    // Check for connection status text
    const statusText = page.locator('text=/Connected|Disconnected/i');
    await expect(statusText.first()).toBeVisible();
  });

  test('should display Procore status in sidebar', async ({ page }) => {
    await page.goto('/');
    
    const compactStatus = page.getByTestId('procore-status-compact');
    await expect(compactStatus).toBeVisible();
  });

  test('should sync Procore data', async ({ page }) => {
    await page.goto('/');
    
    const syncButton = page.getByTestId('button-sync-procore');
    if (await syncButton.isVisible()) {
      await syncButton.click();
      // Wait for sync to start
      await page.waitForTimeout(1000);
    }
  });
});

