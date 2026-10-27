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

/** The OAuth popup is a top-level window whose opener is the embedded app. */
export function isAuthPopup(win: Window = window): boolean {
  try {
    return win.opener != null;
  } catch {
    return false;
  }
}

let cached: IframeContext | null = null;

async function loadHelpers(): Promise<IframeContext> {
  const mod = (await import("@procore/procore-iframe-helpers")) as unknown as { default?: HelpersModule } & HelpersModule;
  const helpers: HelpersModule = mod.default ?? mod;
  return helpers.initialize();
}

export async function getProcoreContext(): Promise<IframeContext | null> {
  if (!isEmbedded()) return null;
  if (cached) return cached;
  cached = await loadHelpers();
  return cached;
}

/** Opens the sign-in window at `url` (the route that starts the OAuth redirect). */
export async function signInThroughProcore(url = "/api/procore/oauth/authorize"): Promise<unknown> {
  const ctx = await getProcoreContext();
  if (!ctx) {
    window.location.assign(url);
    return null;
  }
  return new Promise((resolve, reject) => {
    ctx.authentication.authenticate({
      url,
      onSuccess: (payload) => resolve(payload),
      onFailure: (e) => reject(e instanceof Error ? e : new Error(String(e))),
    });
  });
}

/** Call this from the page the OAuth popup lands on, so the iframe learns that sign-in finished. */
export async function notifySignInDone(payload: unknown = {}): Promise<void> {
  if (!isAuthPopup()) return;
  const ctx = await loadHelpers();
  ctx.authentication.notifySuccess(payload);
}
