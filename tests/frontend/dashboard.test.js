import { afterEach, describe, expect, it, vi } from "vitest";
import {
  bootDashboard,
  createFetch,
  createHealth,
  createSnapshot,
  createUser,
  flushDashboard,
  jsonResponse,
  triggerAutomaticLoad,
} from "./dashboard-test-utils.js";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("credit usage dashboard", () => {
  it("selects English from a non-Chinese browser language and switches every UI layer", async () => {
    const users = [createUser({ status: "medium" })];
    const storageWrite = vi.spyOn(Storage.prototype, "setItem");
    await bootDashboard(
      createFetch({
        snapshot: createSnapshot(users),
        health: createHealth({ status: "error", consecutive_failures: 2 }),
        history: [
          {
            month: "2026-10",
            data_cutoff: "2026-10-31",
            generated_at: "2026-10-31T11:01:59+08:00",
            summary: { users: 1 },
            content_hash: "aaaaaaaa",
            legacy: true,
          },
        ],
      }),
      { language: "en-GB" },
    );

    expect(document.documentElement.lang).toBe("en-US");
    expect(document.title).toBe("Kiro Credits Usage Dashboard");
    expect(document.getElementById("languageToggle").getAttribute("aria-label")).toBe("切换为中文");
    expect(document.getElementById("search").placeholder).toBe("Name or email");
    expect(document.getElementById("timeDelay").textContent).toContain(
      "Kiro source data is typically delayed",
    );
    expect(document.getElementById("dataNotice").textContent).toBe(
      "Usage is cumulative through the data cutoff",
    );
    expect(document.getElementById("healthBanner").textContent).toContain(
      "Data updates are failing",
    );
    expect(document.getElementById("distributionMedium").getAttribute("aria-label")).toBe(
      "Medium usage: 1 users, 100% of evaluable users",
    );
    expect(document.querySelector("#userRows tr").cells[8].textContent).toBe("Medium usage");
    expect(document.querySelector("#userRows tr").cells[10].textContent).toBe(
      "Usage record at the data cutoff",
    );
    expect(document.getElementById("historyList").textContent).toContain("legacy record");

    document.getElementById("languageToggle").click();
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(document.title).toBe("Kiro Credits 用量看板");
    expect(document.getElementById("languageToggle").title).toBe("切换为 English");
    expect(document.getElementById("search").placeholder).toBe("姓名或邮箱");
    expect(document.getElementById("timeDelay").textContent).toContain(
      "Kiro 源数据通常存在 1–2 天延迟",
    );
    expect(document.getElementById("dataNotice").textContent).toBe("用量累计至数据截止日");
    expect(document.getElementById("statusFilter").options[3].textContent).toBe("中使用");
    expect(document.getElementById("healthBanner").textContent).toContain("数据更新异常");
    expect(document.getElementById("distributionMedium").getAttribute("aria-label")).toBe(
      "中使用 1 人，占可评估用户 100%",
    );
    expect(document.querySelector("#userRows tr").cells[8].textContent).toBe("中使用");
    expect(document.getElementById("historyList").textContent).toContain("旧版记录");
    expect(storageWrite).not.toHaveBeenCalled();
  });

  it("selects Chinese for a zh browser language and filters rendered users", async () => {
    const users = [
      createUser({
        user_id: "ada",
        user_name: "Ada Lovelace",
        email: "ada@example.com",
        status: "medium",
      }),
      createUser({
        user_id: "lin",
        user_name: "Lin Qiao",
        email: "lin@example.com",
        status: "zero",
      }),
    ];
    await bootDashboard(
      createFetch({ snapshot: createSnapshot(users), health: createHealth(), history: [] }),
      { language: "zh-Hans-CN" },
    );

    expect(document.documentElement.lang).toBe("zh-CN");
    expect(document.querySelectorAll("#userRows tr")).toHaveLength(2);
    expect(document.getElementById("timeDelay").textContent).toContain(
      "Kiro 源数据通常存在 1–2 天延迟",
    );
    expect(document.getElementById("footerMeta").textContent).toContain(
      "Kiro 源数据通常存在 1–2 天延迟",
    );

    const search = document.getElementById("search");
    search.value = "lin@example.com";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    expect(document.querySelectorAll("#userRows tr")).toHaveLength(1);
    expect(document.querySelector("#userRows td").textContent).toBe("Lin Qiao");

    search.value = "";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    const status = document.getElementById("statusFilter");
    status.value = "zero";
    status.dispatchEvent(new Event("change", { bubbles: true }));
    expect(document.querySelector("#userRows td").textContent).toBe("Lin Qiao");
  });

  it("localizes the token dialog and clears the token after cancellation and submission", async () => {
    const snapshot = createSnapshot();
    const fetchMock = createFetch({ snapshot, health: createHealth() });
    fetchMock.mockImplementation((path, options) => {
      if (path === "/api/refresh") {
        expect(options.headers["X-Refresh-Token"]).toBe("temporary-token");
        return Promise.resolve(jsonResponse({ error: "invalid_refresh_token" }, 401));
      }
      if (path === "/api/current" || path === "/api/reload")
        return Promise.resolve(jsonResponse(snapshot));
      if (path === "/api/health") return Promise.resolve(jsonResponse(createHealth()));
      if (path === "/api/history") return Promise.resolve(jsonResponse({ entries: [] }));
      throw new Error(`Unexpected request: ${path}`);
    });
    await bootDashboard(fetchMock, { language: "en-US" });

    const refresh = document.getElementById("refresh");
    const dialog = document.getElementById("refreshDialog");
    const token = document.getElementById("refreshToken");
    refresh.click();
    expect(document.getElementById("refreshDialogTitle").textContent).toBe("Administrator sync");
    expect(dialog.hidden).toBe(false);
    token.value = "discard-me";
    document.getElementById("refreshCancel").click();
    expect(token.value).toBe("");
    expect(dialog.hidden).toBe(true);

    document.getElementById("languageToggle").click();
    refresh.click();
    expect(document.getElementById("refreshDialogTitle").textContent).toBe("管理员同步");
    expect(document.getElementById("refreshCancel").textContent).toBe("取消");
    token.value = "temporary-token";
    document
      .getElementById("refreshForm")
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(token.value).toBe("");
    expect(dialog.hidden).toBe(true);
    await flushDashboard();
    expect(document.getElementById("toast").textContent).toContain("管理员 Token 无效");
  });

  it("keeps empty last-active values at the bottom for both sort directions", async () => {
    const users = [
      createUser({
        user_id: "empty",
        user_name: "Empty",
        email: "empty@example.com",
        last_active: "",
      }),
      createUser({
        user_id: "late",
        user_name: "Late",
        email: "late@example.com",
        last_active: "2026-11-03",
      }),
      createUser({
        user_id: "early",
        user_name: "Early",
        email: "early@example.com",
        last_active: "2026-11-01",
      }),
    ];
    await bootDashboard(createFetch({ snapshot: createSnapshot(users) }));

    const sortButton = document.querySelector('button[data-sort="last_active"]');
    sortButton.click();
    expect(
      [...document.querySelectorAll("#userRows tr")].map((row) => row.cells[0].textContent),
    ).toEqual(["Early", "Late", "Empty"]);
    expect(sortButton.parentElement.getAttribute("aria-sort")).toBe("ascending");

    sortButton.click();
    expect(
      [...document.querySelectorAll("#userRows tr")].map((row) => row.cells[0].textContent),
    ).toEqual(["Late", "Early", "Empty"]);
    expect(sortButton.parentElement.getAttribute("aria-sort")).toBe("descending");
  });

  it("does not allow a slower load to replace the latest response", async () => {
    const initialSnapshot = createSnapshot([createUser({ user_name: "Initial" })]);
    const newerSnapshot = createSnapshot([createUser({ user_name: "Newest" })]);
    const olderSnapshot = createSnapshot([createUser({ user_name: "Older" })]);
    let resolveOlderRequest;
    const olderRequest = new Promise((resolvePromise) => {
      resolveOlderRequest = resolvePromise;
    });
    let currentRequests = 0;
    const fetchMock = vi.fn((path) => {
      if (path === "/api/current") {
        currentRequests += 1;
        return Promise.resolve(
          jsonResponse(currentRequests === 1 ? initialSnapshot : newerSnapshot),
        );
      }
      if (path === "/api/reload") return olderRequest;
      if (path === "/api/health") return Promise.resolve(jsonResponse(createHealth()));
      if (path === "/api/history") return Promise.resolve(jsonResponse({ entries: [] }));
      throw new Error(`Unexpected request: ${path}`);
    });
    await bootDashboard(fetchMock);

    const reload = document.getElementById("reload");
    reload.click();
    triggerAutomaticLoad();
    await flushDashboard();
    expect(document.querySelector("#userRows td").textContent).toBe("Newest");

    resolveOlderRequest(jsonResponse(olderSnapshot));
    await flushDashboard();
    expect(document.querySelector("#userRows td").textContent).toBe("Newest");
    expect(reload.disabled).toBe(false);
  });
});
