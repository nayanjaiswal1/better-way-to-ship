import { describe, expect, it } from "vitest";

describe("package", () => {
  it("module resolves without error", async () => {
    const pkg = await import("../src/index.js");
    expect(pkg).toBeDefined();
  });
});
