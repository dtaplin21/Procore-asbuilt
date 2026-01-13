# E2E Testing with Playwright

This directory contains end-to-end tests for the Procore Integrator application.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Install Playwright browsers:
```bash
npx playwright install
```

## Running Tests

### Run all tests
```bash
npm run test
```

### Run tests in UI mode (interactive)
```bash
npm run test:ui
```

### Run regression tests only
```bash
npm run test:regression
```

### Run tests in headed mode (see browser)
```bash
npm run test:headed
```

### Run specific test file
```bash
npx playwright test tests/e2e/dashboard.spec.ts
```

## Test Structure

- `tests/e2e/dashboard.spec.ts` - Dashboard page tests
- `tests/e2e/rfis.spec.ts` - RFIs page tests
- `tests/e2e/submittals.spec.ts` - Submittals page tests
- `tests/e2e/navigation.spec.ts` - Navigation flow tests
- `tests/e2e/procore-status.spec.ts` - Procore integration status tests
- `tests/e2e/helpers.ts` - Test helper functions

## Test Tags

Tests marked with `@regression` are part of the regression test suite and can be run with:
```bash
npm run test:regression
```

## CI/CD

Tests automatically run on:
- Push to `main` branch
- Pull requests targeting `main` branch

See `.github/workflows/ci.yml` for CI configuration.

## Writing New Tests

1. Create a new test file in `tests/e2e/`
2. Use `data-testid` attributes to select elements
3. Mark regression tests with `@regression` tag
4. Follow the existing test patterns

Example:
```typescript
import { test, expect } from '@playwright/test';

test.describe('My Feature', () => {
  test('should do something @regression', async ({ page }) => {
    await page.goto('/my-page');
    await expect(page.getByTestId('my-element')).toBeVisible();
  });
});
```

