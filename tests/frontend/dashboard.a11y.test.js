import axe from "axe-core";
import { afterEach, expect, it, vi } from "vitest";
import { bootDashboard, createFetch, createSnapshot } from "./dashboard-test-utils.js";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

it("has no basic accessibility violations in either dashboard language", async () => {
  await bootDashboard(createFetch({ snapshot: createSnapshot() }), { language: "en-US" });

  for (const language of ["en-US", "zh-CN"]) {
    if (language === "zh-CN") document.getElementById("languageToggle").click();
    expect(document.documentElement.lang).toBe(language);
    const results = await axe.run(document, {
      rules: {
        "color-contrast": { enabled: false },
      },
    });
    expect(results.violations).toEqual([]);
  }
});
