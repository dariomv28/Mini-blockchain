import "@testing-library/jest-dom";
import { vi } from "vitest";

// Mock window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Mock clipboard
Object.defineProperty(navigator, "clipboard", {
  value: {
    writeText: async () => Promise.resolve(),
  },
  configurable: true,
});

// Polyfill global fetch for Node 16 / jsdom test environment
if (!global.fetch) {
  global.fetch = vi.fn().mockImplementation(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({}),
      text: async () => "",
      clone: () => ({ json: async () => ({}) }),
    })
  ) as any;
}
