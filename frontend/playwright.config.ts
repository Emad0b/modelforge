import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: process.env.PREVIEW_URL || "http://127.0.0.1:5175",
    headless: true,
  },
  reporter: "list",
});
