import { test, expect, type Page } from '@playwright/test';

const DRAWING_URL = '/projects/1/drawings/10/workspace';

/** 1x1 transparent PNG so img loads in tests */
const DATA_URL_1X1_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

const mockDrawing = {
  id: 10,
  projectId: 1,
  source: 'master',
  name: 'Level 1 Master Plan',
  fileUrl: DATA_URL_1X1_PNG,
  sourceFileUrl: '/api/projects/1/drawings/10/file',
  contentType: 'application/pdf',
  pageCount: 1,
  activePage: 1,
  widthPx: 800,
  heightPx: 600,
  processingStatus: 'ready',
  processingError: null,
};

async function mockWorkspaceApis(page: Page) {
  await page.route(/\/api\/projects\/1\/dashboard\/summary/, (route) =>
    route.fulfill({
      json: {
        current_drawing: { id: 10, name: 'Level 1 Master Plan' },
      },
    })
  );
  await page.route(/\/api\/projects\/1\/inspections\/runs/, (route) =>
    route.fulfill({ json: { items: [] } })
  );
  await page.route(/\/api\/projects\/1\/evidence/, (route) =>
    route.fulfill({ json: { items: [] } })
  );
  await page.route(/\/api\/projects\/1\/drawings\/10\/overlays/, (route) =>
    route.fulfill({ json: [] })
  );
}

test.describe('Drawing Workspace', () => {
  test('loads the master drawing and inspection sidebar', async ({ page }) => {
    await mockWorkspaceApis(page);
    await page.route(/\/api\/projects\/1\/drawings\/10$/, (route) =>
      route.fulfill({ json: mockDrawing })
    );

    await page.goto(DRAWING_URL);

    await expect(page.getByText('Level 1 Master Plan')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Drawing #10')).toBeVisible();
    await expect(page.getByTestId('inspection-runs-panel')).toBeVisible();
  });

  test('retry reloads the workspace after a drawing fetch failure', async ({ page }) => {
    let drawingFail = true;

    await mockWorkspaceApis(page);
    await page.route(/\/api\/projects\/1\/drawings\/10$/, (route) => {
      if (drawingFail) {
        return route.fulfill({ status: 500, json: { detail: 'Server error' } });
      }
      return route.fulfill({ json: mockDrawing });
    });

    await page.goto(DRAWING_URL);

    await expect(page.getByText('Workspace failed to load')).toBeVisible({ timeout: 5000 });

    drawingFail = false;
    await page.getByTestId('retry-workspace').click();

    await expect(page.getByText('Level 1 Master Plan')).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId('drawing-viewer-image')).toBeVisible();
  });
});

test.describe('drawing workspace viewer', () => {
  test('supports zoom, pan, and reset', async ({ page }) => {
    await mockWorkspaceApis(page);
    await page.route(/\/api\/projects\/1\/drawings\/10$/, (route) =>
      route.fulfill({ json: mockDrawing })
    );

    await page.goto(DRAWING_URL);

    await expect(page.getByTestId('drawing-viewer-image')).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId('pan-zoom-container')).toBeVisible();

    await expect(page.getByText(/Zoom:/)).toContainText('100%');

    const panZoomContainer = page.getByTestId('pan-zoom-container');
    await panZoomContainer.hover();

    await page.mouse.wheel(0, -500);

    await expect(page.getByText(/Zoom:/)).not.toContainText('100%');

    const content = page.getByTestId('pan-zoom-content');
    const transformBefore = await content.getAttribute('style');

    const box = await panZoomContainer.boundingBox();
    if (!box) throw new Error('Pan zoom container not found');

    await page.mouse.move(box.x + 150, box.y + 150);
    await page.mouse.down();
    await page.mouse.move(box.x + 260, box.y + 240, { steps: 6 });
    await page.mouse.up();

    const transformAfter = await content.getAttribute('style');
    expect(transformAfter).not.toBe(transformBefore);

    await page.getByRole('button', { name: 'Reset view' }).click();
    await expect(page.getByText(/Zoom:/)).toContainText('100%');
  });
});
