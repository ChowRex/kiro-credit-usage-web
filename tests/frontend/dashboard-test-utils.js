import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { vi } from "vitest";

const directory = dirname(fileURLToPath(import.meta.url));
const indexHtml = readFileSync(resolve(directory, "../../web/index.html"), "utf8");
const applicationScript = readFileSync(resolve(directory, "../../web/app.js"), "utf8");

let automaticLoad;

export function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(payload),
  };
}

export function createUser(overrides = {}) {
  return {
    user_id: "user-1",
    user_name: "Ada Lovelace",
    email: "ada@example.com",
    tier: "Pro",
    credits: 100,
    overage: 0,
    capacity: 1000,
    usage_percent: 10,
    first_active: "2026-11-01",
    last_active: "2026-11-01",
    active_days: 1,
    status: "medium",
    monthly_cost_usd: 20,
    tier_source: "latest_at_data_cutoff",
    ...overrides,
  };
}

export function createSnapshot(users = [createUser()]) {
  const counts = Object.fromEntries(
    ["zero", "low", "medium", "normal", "high", "unknown"].map((status) => [
      status,
      users.filter((user) => user.status === status).length,
    ]),
  );
  return {
    schema_version: 1,
    generated_at: "2026-11-02T11:01:59+08:00",
    month: "2026-11",
    data_cutoff: "2026-11-01",
    no_month_data: false,
    roster_source: "iam_identity_center",
    source_lag_warning: "Kiro 源数据通常存在 1–2 天延迟",
    usage_interpretation: "用量累计至数据截止日",
    summary: {
      users: users.length,
      ...counts,
      total_credits: users.reduce((total, user) => total + user.credits, 0),
      known_monthly_cost_usd: users.reduce(
        (total, user) => total + (user.monthly_cost_usd || 0),
        0,
      ),
      unknown_cost_users: users.filter((user) => user.monthly_cost_usd == null).length,
    },
    collection: {
      data_scanned_bytes: 1024,
      engine_execution_ms: 10,
      query_count: 1,
      total_execution_ms: 10,
    },
    users,
  };
}

export function createHealth(overrides = {}) {
  return {
    status: "success",
    has_snapshot: true,
    serving_stale_snapshot: false,
    snapshot_age_hours: 1,
    stale_after_hours: 24,
    last_checked_at: "2026-11-02T11:01:59+08:00",
    last_success_at: "2026-11-02T11:01:59+08:00",
    consecutive_failures: 0,
    next_retry_at: null,
    last_error: null,
    manual_refresh_enabled: true,
    manual_refresh_running: false,
    snapshot_generated_at: "2026-11-02T11:01:59+08:00",
    snapshot_data_cutoff: "2026-11-01",
    ...overrides,
  };
}

export function createFetch({ snapshot, health = createHealth(), history = [] }) {
  return vi.fn((path) => {
    if (path === "/api/current" || path === "/api/reload")
      return Promise.resolve(jsonResponse(snapshot));
    if (path === "/api/health") return Promise.resolve(jsonResponse(health));
    if (path === "/api/history") return Promise.resolve(jsonResponse({ entries: history }));
    throw new Error(`Unexpected request: ${path}`);
  });
}

export async function flushDashboard() {
  await new Promise((resolvePromise) => window.setTimeout(resolvePromise, 0));
}

export function triggerAutomaticLoad() {
  automaticLoad();
}

export async function bootDashboard(fetchMock, { language = "zh-CN" } = {}) {
  const parsed = new DOMParser().parseFromString(indexHtml, "text/html");
  parsed.querySelectorAll("script").forEach((script) => script.remove());
  Object.defineProperty(window.navigator, "language", { configurable: true, value: language });
  document.documentElement.lang = parsed.documentElement.lang;
  document.head.replaceChildren(
    ...[...parsed.head.children].map((element) => element.cloneNode(true)),
  );
  document.body.replaceChildren(
    ...[...parsed.body.children].map((element) => element.cloneNode(true)),
  );
  vi.spyOn(window, "setInterval").mockImplementation((callback) => {
    automaticLoad = callback;
    return 0;
  });
  vi.stubGlobal("fetch", fetchMock);
  window.fetch = fetchMock;
  window.eval(`(() => {\n${applicationScript}\n})();`);
  await flushDashboard();
}
