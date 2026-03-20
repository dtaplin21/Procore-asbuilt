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
