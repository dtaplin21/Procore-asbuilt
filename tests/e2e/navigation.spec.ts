import { test, expect } from '@playwright/test';

test.describe('Navigation Flow', () => {
  test('should navigate through all main pages @regression', async ({ page }) => {
    await page.goto('/');

    // Dashboard
    await expect(page.getByTestId('text-page-title')).toHaveText('Dashboard');
    
    // Navigate to Submittals
    await page.getByTestId('nav-submittals').click();
    await expect(page).toHaveURL('/submittals');
    await expect(page.getByTestId('text-page-title')).toHaveText('Submittals');
    
    // Navigate to RFIs
    await page.getByTestId('nav-rfis').click();
    await expect(page).toHaveURL('/rfis');
    await expect(page.getByTestId('text-page-title')).toHaveText('RFIs');
    
    // Navigate to Inspections
    await page.getByTestId('nav-inspections').click();
    await expect(page).toHaveURL('/inspections');
    await expect(page.getByTestId('text-page-title')).toHaveText('Inspections');
    
    // Navigate to Objects
    await page.getByTestId('nav-objects').click();
    await expect(page).toHaveURL('/objects');
    await expect(page.getByTestId('text-page-title')).toHaveText('Objects');
    
    // Navigate to Settings
    await page.getByTestId('nav-settings').click();
    await expect(page).toHaveURL('/settings');
    await expect(page.getByTestId('text-page-title')).toHaveText('Settings');
  });

  test('should toggle sidebar', async ({ page }) => {
    await page.goto('/');
    
    const sidebarToggle = page.getByTestId('button-sidebar-toggle');
    await expect(sidebarToggle).toBeVisible();
    await sidebarToggle.click();
    // Sidebar should collapse/expand
    await page.waitForTimeout(300);
  });
});

