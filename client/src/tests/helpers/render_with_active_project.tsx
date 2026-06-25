import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation as useRouterLocation,
  useNavigate,
} from "react-router-dom";
import { Router } from "wouter";
import type { ReactElement } from "react";

import { ActiveProjectProvider } from "@/contexts/active_project_context";

function useWouterFromReactRouter(): [string, (to: string) => void] {
  const { pathname, search } = useRouterLocation();
  const navigate = useNavigate();
  return [`${pathname}${search}`, (to: string) => navigate(to)];
}

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

export function renderActiveProjectPage(
  path: string,
  initialEntry: string,
  page: ReactElement,
  options?: { queryClient?: QueryClient; siblings?: ReactElement },
): RenderResult {
  const queryClient = options?.queryClient ?? createTestQueryClient();
  const element = options?.siblings ? (
    <>
      {page}
      {options.siblings}
    </>
  ) : (
    page
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Router hook={useWouterFromReactRouter}>
          <ActiveProjectProvider>
            <Routes>
              <Route path={path} element={element} />
            </Routes>
          </ActiveProjectProvider>
        </Router>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function renderWithActiveProjectRoutes(
  initialEntry: string,
  routes: Array<{ path: string; element: ReactElement }>,
  queryClient?: QueryClient,
): RenderResult {
  const client = queryClient ?? createTestQueryClient();

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Router hook={useWouterFromReactRouter}>
          <ActiveProjectProvider>
            <Routes>
              {routes.map((route) => (
                <Route key={route.path} path={route.path} element={route.element} />
              ))}
            </Routes>
          </ActiveProjectProvider>
        </Router>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
