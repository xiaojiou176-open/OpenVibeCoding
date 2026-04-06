import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    include: ["lib/**/*.test.ts"],
    globals: true,
    pool: "forks",
    maxWorkers: 1,
    fileParallelism: false,
    testTimeout: 15000,
  },
});
