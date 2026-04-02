import { test, expect } from '@playwright/test';

const DRAWING_URL = '/projects/1/drawings/10/workspace';

const mockDrawing = {
  id: 10,
  projectId: 1,
  source: 'master',
  name: 'Level 1 Master Plan',
  fileUrl: '/uploads/drawings/master-10.pdf',
  contentType: 'application/pdf',
  pageCount: 1,
};

const mockAlignments = [
  {
    id: 1,
    projectId: 1,
    masterDrawingId: 10,
    subDrawingId: 101,
    alignmentStatus: 'complete',
    subDrawing: { id: 101, name: 'Sub A' },
    createdAt: '2025-02-13T12:00:00Z',
  },
  {
    id: 2,
    projectId: 1,
    masterDrawingId: 10,
    subDrawingId: 102,
    alignmentStatus: 'complete',
    subDrawing: { id: 102, name: 'Sub B' },
    createdAt: '2025-02-12T10:00:00Z',
  },
];

/** 1x1 transparent PNG so img loads in tests */
const DATA_URL_1X1_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

const mockDrawingWithOverlays = {
  id: 10,
  projectId: 1,
  source: 'master',
  name: 'Level 1 Master Plan',
  fileUrl: DATA_URL_1X1_PNG,
  sourceFileUrl: '/api/projects/1/drawings/10/file',
  pageCount: 1,
  activePage: 1,
  widthPx: 800,
  heightPx: 600,
  processingStatus: 'ready',
  processingError: null,
};

const mockDiffsWithOverlays = {
  diffs: [
    {
      id: 1,
      alignmentId: 1,
      summary: 'Diff 1',
      severity: 'low',
      createdAt: '2025-02-13T14:00:00Z',
      diffRegions: [
        {
          shapeType: 'rect',
          rect: { x: 0.1, y: 0.2, width: 0.25, height: 0.15 },
        },
      ],
    },
    {
      id: 2,
      alignmentId: 1,
      summary: 'Diff 2',
      severity: 'medium',
      createdAt: '2025-02-13T13:00:00Z',
      diffRegions: [
        {
          shapeType: 'polygon',
          points: [
            { x: 0.2, y: 0.3 },
            { x: 0.4, y: 0.3 },
            { x: 0.3, y: 0.5 },
          ],
        },
      ],
    },
  ],
};

const mockDiffsA = {
  diffs: [
    { id: 1, alignmentId: 1, summary: 'Diff 1', severity: 'low', createdAt: '2025-02-13T14:00:00Z', diffRegions: [] },
    { id: 2, alignmentId: 1, summary: 'Diff 2', severity: 'medium', createdAt: '2025-02-13T13:00:00Z', diffRegions: [] },
  ],
};

const mockDiffsB = {
  diffs: [
    { id: 3, alignmentId: 2, summary: 'Diff 3', severity: 'high', createdAt: '2025-02-12T11:00:00Z', diffRegions: [] },
  ],
};

test.describe('Drawing Workspace', () => {
  test('A. Valid page load - drawing, alignments, and diffs load; newest alignment selected', async ({ page }) => {
    await page.route(/\/api\/projects\/1\/drawings\/10\/alignments$/, (route) =>
      route.fulfill({ json: { alignments: mockAlignments } })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/diffs/, (route) => {
      const url = new URL(route.request().url());
      const alignmentId = url.searchParams.get('alignment_id');
      if (alignmentId === '1') return route.fulfill({ json: mockDiffsA });
      if (alignmentId === '2') return route.fulfill({ json: mockDiffsB });
      return route.fulfill({ json: { diffs: [] } });
    });
    await page.route(/\/api\/projects\/1\/drawings\/10$/, (route) =>
      route.fulfill({ json: mockDrawing })
    );

    await page.goto(DRAWING_URL);

    await expect(page.getByText('Level 1 Master Plan')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Drawing #10')).toBeVisible();
    await expect(page.getByText('Sub A')).toBeVisible();
    await expect(page.getByText('Sub B')).toBeVisible();

    const alignment1 = page.getByTestId('alignment-1');
    await expect(alignment1).toHaveClass(/bg-slate-100/);

    await expect(page.getByText('Diff 1')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Diff 2')).toBeVisible();
  });

  test('B. No alignments case - selected alignment null, no diffs request, empty state', async ({ page }) => {
    let diffsRequestCount = 0;
    await page.route('**/api/projects/1/drawings/10', (route) => {
      if (route.request().url().endsWith('/10') && !route.request().url().includes('alignments') && !route.request().url().includes('diffs')) {
        return route.fulfill({ json: mockDrawing });
      }
      return route.continue();
    });
    await page.route('**/api/projects/1/drawings/10/alignments', (route) =>
      route.fulfill({ json: { alignments: [] } })
    );
    await page.route('**/api/projects/1/drawings/10/diffs*', (route) => {
      diffsRequestCount++;
      return route.fulfill({ json: { diffs: [] } });
    });

    await page.goto(DRAWING_URL);

    await expect(page.getByText('Level 1 Master Plan')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('No alignments found.')).toBeVisible();

    expect(diffsRequestCount).toBe(0);
    await expect(page.getByText('No diffs for the selected alignment.')).toBeVisible();
    await expect(page.getByText('No alignments found.')).toBeVisible();
  });

  test('C. Switch alignment - diffs load for new alignment, timeline updates', async ({ page }) => {
    await page.route('**/api/projects/1/drawings/10', (route) => {
      if (route.request().url().endsWith('/10') && !route.request().url().includes('alignments') && !route.request().url().includes('diffs')) {
        return route.fulfill({ json: mockDrawing });
      }
      return route.continue();
    });
    await page.route('**/api/projects/1/drawings/10/alignments', (route) =>
      route.fulfill({ json: { alignments: mockAlignments } })
    );
    await page.route('**/api/projects/1/drawings/10/diffs*', (route) => {
      const url = new URL(route.request().url());
      const alignmentId = url.searchParams.get('alignment_id');
      if (alignmentId === '1') return route.fulfill({ json: mockDiffsA });
      if (alignmentId === '2') return route.fulfill({ json: mockDiffsB });
      return route.fulfill({ json: { diffs: [] } });
    });

    await page.goto(DRAWING_URL);

    await expect(page.getByText('Diff 1')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('alignment-2').click();
    await expect(page.getByTestId('alignment-2')).toHaveClass(/bg-slate-100/);
    await expect(page.getByText('Diff 3')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Diff 1')).not.toBeVisible();
  });

  test('D. Retry behavior - workspace retry and diff retry work', async ({ page }) => {
    let drawingFail = true;
    let alignmentsFail = true;
    let diffsFail = true;

    await page.route('**/api/projects/1/drawings/10', (route) => {
      const url = route.request().url();
      if (url.includes('alignments') || url.includes('diffs')) return route.continue();
      if (drawingFail) return route.fulfill({ status: 500, json: { detail: 'Server error' } });
      return route.fulfill({ json: mockDrawing });
    });
    await page.route('**/api/projects/1/drawings/10/alignments', (route) => {
      if (alignmentsFail) return route.fulfill({ status: 500, json: { detail: 'Server error' } });
      return route.fulfill({ json: { alignments: mockAlignments } });
    });
    await page.route('**/api/projects/1/drawings/10/diffs*', (route) => {
      if (diffsFail) return route.fulfill({ status: 500, json: { detail: 'Server error' } });
      return route.fulfill({ json: mockDiffsA });
    });

    await page.goto(DRAWING_URL);

    await expect(page.getByText('Failed to load workspace')).toBeVisible({ timeout: 5000 });
    drawingFail = false;
    alignmentsFail = false;
    await page.getByTestId('retry-workspace').click();
    await expect(page.getByText('Level 1 Master Plan')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Failed to load diffs')).toBeVisible({ timeout: 3000 });

    diffsFail = false;
    await page.getByTestId('retry-diffs').click();
    await expect(page.getByText('Diff 1')).toBeVisible({ timeout: 5000 });
  });

  test('E. Cache behavior - diffs for A reused when switching back', async ({ page }) => {
    const diffsRequestLog: number[] = [];
    await page.route('**/api/projects/1/drawings/10', (route) => {
      if (route.request().url().endsWith('/10') && !route.request().url().includes('alignments') && !route.request().url().includes('diffs')) {
        return route.fulfill({ json: mockDrawing });
      }
      return route.continue();
    });
    await page.route('**/api/projects/1/drawings/10/alignments', (route) =>
      route.fulfill({ json: { alignments: mockAlignments } })
    );
    await page.route('**/api/projects/1/drawings/10/diffs*', (route) => {
      const url = new URL(route.request().url());
      const alignmentId = parseInt(url.searchParams.get('alignment_id') ?? '0', 10);
      diffsRequestLog.push(alignmentId);
      if (alignmentId === 1) return route.fulfill({ json: mockDiffsA });
      if (alignmentId === 2) return route.fulfill({ json: mockDiffsB });
      return route.fulfill({ json: { diffs: [] } });
    });

    await page.goto(DRAWING_URL);

    await expect(page.getByText('Diff 1')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('alignment-2').click();
    await expect(page.getByText('Diff 3')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('alignment-1').click();
    await expect(page.getByText('Diff 1')).toBeVisible({ timeout: 3000 });

    const alignment1Requests = diffsRequestLog.filter((id) => id === 1);
    expect(alignment1Requests.length).toBe(1);
  });
});

test.describe('drawing workspace viewer', () => {
  test('supports zoom, pan, and reset', async ({ page }) => {
    await page.route(/\/api\/projects\/1\/drawings\/10$/, (route) =>
      route.fulfill({ json: mockDrawingWithOverlays })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/alignments$/, (route) =>
      route.fulfill({ json: { alignments: mockAlignments } })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/diffs/, (route) => {
      const url = new URL(route.request().url());
      const alignmentId = url.searchParams.get('alignment_id');
      if (alignmentId === '1') return route.fulfill({ json: mockDiffsWithOverlays });
      if (alignmentId === '2') return route.fulfill({ json: mockDiffsA });
      return route.fulfill({ json: { diffs: [] } });
    });

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

test.describe('drawing workspace overlays', () => {

  test('switching selected diff keeps overlay rendering visible', async ({
    page,
  }) => {
    await page.route(/\/api\/projects\/1\/drawings\/10$/, (route) =>
      route.fulfill({ json: mockDrawingWithOverlays })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/alignments$/, (route) =>
      route.fulfill({ json: { alignments: mockAlignments } })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/diffs/, (route) =>
      route.fulfill({ json: mockDiffsWithOverlays })
    );

    await page.goto(DRAWING_URL);

    await expect(page.getByTestId('drawing-viewer-image')).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByTestId('drawing-overlay-layer')).toBeVisible({
      timeout: 3000,
    });

    const diff1 = page.getByTestId('diff-1');
    const diff2 = page.getByTestId('diff-2');
    await expect(diff1).toBeVisible();
    await expect(diff2).toBeVisible();

    await diff2.click();
    await expect(page.getByTestId('drawing-overlay-layer')).toBeVisible();
  });
});

test.describe('compare sub drawing', () => {
  test('opens modal, posts compare, closes on success, updates alignments, diffs, and viewer', async ({
    page,
  }) => {
    let comparePosted: unknown;
    const compareResponse = {
      masterDrawing: null,
      subDrawing: { id: 201, projectId: 1, name: 'Compare pick', source: 'procore' },
      alignment: {
        id: 3,
        projectId: 1,
        masterDrawingId: 10,
        subDrawingId: 201,
        alignmentStatus: 'complete',
        subDrawing: { id: 201, name: 'Compare pick' },
        createdAt: '2025-02-15T12:00:00Z',
      },
      diffs: [
        {
          id: 501,
          alignmentId: 3,
          summary: 'From compare',
          severity: 'high',
          createdAt: '2025-02-15T12:00:00Z',
          diffRegions: [
            {
              shapeType: 'rect',
              rect: { x: 0.1, y: 0.1, width: 0.2, height: 0.2 },
            },
          ],
        },
      ],
    };

    await page.route(
      (url) => url.pathname === '/api/projects/1/drawings',
      (route) =>
        route.fulfill({
          json: {
            drawings: [
              { id: 201, projectId: 1, name: 'Compare pick', source: 'procore' },
            ],
          },
        })
    );

    await page.route('**/api/projects/1/drawings/compare/10/201', async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      comparePosted = route.request().postData();
      await new Promise((r) => setTimeout(r, 50));
      await route.fulfill({ json: compareResponse });
    });

    await page.route(/\/api\/projects\/1\/drawings\/10$/, (route) =>
      route.fulfill({ json: mockDrawing })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/alignments$/, (route) =>
      route.fulfill({ json: { alignments: mockAlignments } })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/diffs/, (route) => {
      const url = new URL(route.request().url());
      const alignmentId = url.searchParams.get('alignment_id');
      if (alignmentId === '1') return route.fulfill({ json: mockDiffsA });
      if (alignmentId === '2') return route.fulfill({ json: mockDiffsB });
      if (alignmentId === '3')
        return route.fulfill({ json: { diffs: compareResponse.diffs } });
      return route.fulfill({ json: { diffs: [] } });
    });

    await page.goto(DRAWING_URL);

    await expect(page.getByText('Sub A')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('compare-sub-drawing-button').click();
    await expect(page.getByTestId('compare-sub-drawing-modal')).toBeVisible();

    await page.getByTestId('sub-drawing-item-201').click();
    await page.getByTestId('confirm-compare-sub-drawing-button').click();

    await expect(page.getByTestId('confirm-compare-sub-drawing-button')).toHaveText(
      'Comparing...'
    );

    await expect(
      page.locator('[data-testid="compare-sub-drawing-modal"]')
    ).toHaveCount(0, { timeout: 8000 });

    expect(comparePosted).toBeNull();

    await expect(page.getByTestId('alignment-3')).toBeVisible();
    await expect(page.getByTestId('alignment-3')).toHaveClass(/bg-slate-100/);

    await expect(page.getByTestId('diff-501')).toBeVisible();
    await expect(page.getByText(/Selected diff #501/)).toBeVisible();
  });

  test('compare failure keeps modal open with error; retry succeeds', async ({ page }) => {
    let compareCalls = 0;
    const successPayload = {
      masterDrawing: null,
      subDrawing: { id: 201, projectId: 1, name: 'Compare pick', source: 'procore' },
      alignment: {
        id: 3,
        projectId: 1,
        masterDrawingId: 10,
        subDrawingId: 201,
        alignmentStatus: 'complete',
        subDrawing: { id: 201, name: 'Compare pick' },
        createdAt: '2025-02-15T12:00:00Z',
      },
      diffs: [
        {
          id: 501,
          alignmentId: 3,
          summary: 'Retry ok',
          severity: 'low',
          createdAt: '2025-02-15T12:00:00Z',
          diffRegions: [],
        },
      ],
    };

    await page.route(
      (url) => url.pathname === '/api/projects/1/drawings',
      (route) =>
        route.fulfill({
          json: {
            drawings: [
              { id: 201, projectId: 1, name: 'Compare pick', source: 'procore' },
            ],
          },
        })
    );

    await page.route('**/api/projects/1/drawings/compare/10/201', async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      compareCalls++;
      if (compareCalls === 1) {
        return route.fulfill({ status: 500, json: { detail: 'Compare failed' } });
      }
      return route.fulfill({ json: successPayload });
    });

    await page.route(/\/api\/projects\/1\/drawings\/10$/, (route) =>
      route.fulfill({ json: mockDrawing })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/alignments$/, (route) =>
      route.fulfill({ json: { alignments: mockAlignments } })
    );
    await page.route(/\/api\/projects\/1\/drawings\/10\/diffs/, (route) => {
      const url = new URL(route.request().url());
      const alignmentId = url.searchParams.get('alignment_id');
      if (alignmentId === '1') return route.fulfill({ json: mockDiffsA });
      if (alignmentId === '2') return route.fulfill({ json: mockDiffsB });
      if (alignmentId === '3')
        return route.fulfill({ json: { diffs: successPayload.diffs } });
      return route.fulfill({ json: { diffs: [] } });
    });

    await page.goto(DRAWING_URL);
    await expect(page.getByText('Sub A')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('compare-sub-drawing-button').click();
    await page.getByTestId('sub-drawing-item-201').click();
    await page.getByTestId('confirm-compare-sub-drawing-button').click();

    await expect(page.getByText('Compare failed')).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId('compare-sub-drawing-modal')).toBeVisible();

    await page.getByTestId('confirm-compare-sub-drawing-button').click();
    await expect(
      page.locator('[data-testid="compare-sub-drawing-modal"]')
    ).toHaveCount(0, { timeout: 8000 });
  });
});
