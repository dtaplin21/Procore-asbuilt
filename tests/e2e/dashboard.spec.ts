import { test, expect } from '@playwright/test';

test.describe('Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should load dashboard page @regression', async ({ page }) => {
    // Check page title
    await expect(page.getByTestId('text-page-title')).toHaveText('Dashboard');
    
    // Check for stat cards
    const statCards = page.locator('[data-testid^="stat-card-"]');
    await expect(statCards.first()).toBeVisible();
  });

  test('should display Procore status', async ({ page }) => {
    const procoreStatus = page.getByTestId('procore-status');
    await expect(procoreStatus).toBeVisible();
  });

  test('should navigate to submittals page', async ({ page }) => {
    await page.getByTestId('nav-submittals').click();
    await expect(page).toHaveURL('/submittals');
  });

  test('should navigate to RFIs page', async ({ page }) => {
    await page.getByTestId('nav-rfis').click();
    await expect(page).toHaveURL('/rfis');
  });
});

