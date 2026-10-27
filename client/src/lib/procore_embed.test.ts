import { describe, expect, it, vi } from "vitest";

const notifySuccess = vi.hoisted(() => vi.fn());

vi.mock("@procore/procore-iframe-helpers", () => {
  const api = { initialize: () => ({ authentication: { notifySuccess } }) };
  return { ...api, default: api };
});

import { isAuthPopup, isEmbedded, notifySignInDone, signInThroughProcore } from "./procore_embed";

describe("procore_embed", () => {
  it("is not embedded in a top-level window", () => {
    expect(isEmbedded()).toBe(false);
  });
  it("treats a throwing cross-origin top as embedded", () => {
    const win = { self: {}, get top(): never { throw new Error("blocked"); } } as unknown as Window;
    expect(isEmbedded(win)).toBe(true);
  });
  it("signs in with a plain redirect outside Procore", async () => {
    const assign = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", { value: { ...original, assign }, configurable: true });
    await signInThroughProcore("/auth/procore");
    expect(assign).toHaveBeenCalledWith("/auth/procore");
    Object.defineProperty(window, "location", { value: original, configurable: true });
  });
  it("tells the embedded app that the sign-in popup finished", async () => {
    Object.defineProperty(window, "opener", { configurable: true, value: {} });
    expect(isAuthPopup()).toBe(true);
    await notifySignInDone({ userId: "42", companyId: "7" });
    expect(notifySuccess).toHaveBeenCalledWith({ userId: "42", companyId: "7" });
    Object.defineProperty(window, "opener", { configurable: true, value: null });
  });
  it("does not notify from a normal tab", async () => {
    Object.defineProperty(window, "opener", { configurable: true, value: null });
    notifySuccess.mockClear();
    await notifySignInDone({ userId: "42" });
    expect(notifySuccess).not.toHaveBeenCalled();
  });
});
