/**
 * Embedded-app bridge. Procore's login page will not render inside an iframe, so sign-in opens a
 * separate window and hands the result back to the iframe. The package is archived on GitHub.
 */
interface IframeContext {
  authentication: {
    authenticate(opts: { url: string; onSuccess: (payload: unknown) => void; onFailure: (error: unknown) => void }): void;
    notifySuccess(payload?: unknown): void;
  };
}
interface HelpersModule {
  initialize(): IframeContext;
}

export function isEmbedded(win: Window = window): boolean {
  try {
    return win.self !== win.top;
  } catch {
    return true;
  }
}

let cached: IframeContext | null = null;

export async function getProcoreContext(): Promise<IframeContext | null> {
  if (!isEmbedded()) return null;
  if (cached) return cached;
  const mod = (await import("@procore/procore-iframe-helpers")) as unknown as { default?: HelpersModule } & HelpersModule;
  const helpers: HelpersModule = mod.default ?? mod;
  cached = helpers.initialize();
  return cached;
}

/** Opens the sign-in window at `url` (a route on your server that starts the OAuth redirect). */
export async function signInThroughProcore(url = "/auth/procore"): Promise<void> {
  const ctx = await getProcoreContext();
  if (!ctx) {
    window.location.assign(url);
    return;
  }
  await new Promise<void>((resolve, reject) => {
    ctx.authentication.authenticate({ url, onSuccess: () => resolve(), onFailure: (e) => reject(e instanceof Error ? e : new Error(String(e))) });
  });
}

/** Call this from the page your OAuth callback renders, so the iframe learns that sign-in finished. */
export async function notifySignInDone(): Promise<void> {
  const ctx = await getProcoreContext();
  ctx?.authentication.notifySuccess({});
}
