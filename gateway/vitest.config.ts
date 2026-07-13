import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    // The bridge retries failed requests with a linear backoff (1s + 2s + 3s
    // between four attempts), so tests that exercise the connection-failure
    // path against a dead port take ~6s each. Raise the per-test timeout above
    // vitest's 5s default so those cases complete instead of timing out.
    testTimeout: 30000,
  },
});
