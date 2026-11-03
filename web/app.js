const MESSAGES = {
  "zh-CN": {
    pageTitle: "Kiro Credits 用量看板",
    eyebrow: "KIRO 企业版 · 内部",
    loadingSnapshot: "正在读取最新成功快照…",
    reload: "重新读取",
    refresh: "立即同步 AWS",
    downloadCsv: "下载 CSV",
    switchToEnglish: "切换为 English",
    switchToChinese: "切换为中文",
    checkingRefresh: "正在检查刷新状态…",
    loadingInterpretation: "正在读取数据口径…",
    dataTime: "数据时间",
    browserTime: "以下时间按浏览器本地时间显示",
    dataCutoff: "数据截止日",
    snapshotGenerated: "快照生成时间",
    lastSuccessfulRefresh: "最后成功刷新",
    dataFreshness: "数据时效",
    loadingFreshness: "正在读取数据时效说明…",
    overviewKicker: "总体概览",
    overview: "总体概览",
    overviewDescription: "组织当前资源与采集成本",
    totalUsers: "总用户",
    currentRoster: "当前订阅名册",
    totalCredits: "累计 Credits",
    throughLatestDataDay: "截至最新数据日",
    knownMonthlyCost: "月成本合计（已知）",
    athenaScanned: "Athena 扫描",
    accountStatusKicker: "账户状态",
    accountStatus: "账户状态",
    accountStatusDescription: "根据数据截止日前的用量证据判断",
    active: "活跃",
    unknownStatus: "未知状态",
    usageDistributionKicker: "用户用量分布",
    usageDistribution: "用户用量分布",
    statusZero: "零使用",
    statusLow: "低使用",
    statusMedium: "中使用",
    statusNormal: "正常",
    statusHigh: "高负载",
    statusUnknown: "套餐/容量未知",
    distributionZeroDescription: "本月无 Credits · ",
    distributionLowDescription: "非零且低于 10% · ",
    distributionMediumDescription: "10%–<50% · ",
    distributionNormalDescription: "50%–80% · ",
    distributionHighDescription: "超过 80% · ",
    userDetails: "用户明细",
    loading: "正在加载…",
    search: "搜索",
    searchPlaceholder: "姓名或邮箱",
    status: "状态",
    allStatuses: "全部状态",
    tier: "套餐",
    allTiers: "全部套餐",
    user: "用户",
    email: "邮箱",
    creditsCapacity: "Credits / 容量",
    usageRate: "使用率",
    lastActive: "最后活跃",
    activeDays: "活跃天数",
    monthlyCost: "月成本",
    tierSource: "套餐来源",
    noMatchingUsers: "没有符合当前筛选条件的用户。",
    recentSnapshots: "最近快照",
    historyDescription: "永久历史中的最近 5 次有效记录，仅展示摘要。",
    noHistory: "暂无历史快照。",
    adminSync: "管理员同步",
    refreshDialogDescription:
      "请输入管理员 Token 以启动 AWS 数据同步。Token 仅用于本次请求，不会保存在浏览器中。",
    adminToken: "管理员 Token",
    cancel: "取消",
    startSync: "启动同步",
    notAvailable: "N/A",
    noSnapshot: "尚无可用数据快照，请由管理员执行数据刷新。",
    refreshRunning: "正在刷新数据，页面继续显示最后成功快照。最后成功：{time}。",
    staleSnapshot:
      "数据更新异常，正在继续显示最后成功快照。最后成功：{time}；连续失败：{failures}。",
    healthNormal: "数据服务正常。最后成功刷新：{time}。",
    refreshEnabledTitle: "使用管理员 Token 启动 AWS 数据同步",
    refreshDisabledTitle: "服务端未启用管理员同步",
    noMonthData: "本月暂无可用数据",
    noFreshnessNotice: "暂无数据时效说明",
    sourceLagWarning: "Kiro 源数据通常存在 1–2 天延迟",
    usageCumulative: "用量累计至数据截止日",
    usageNoCurrentMonth: "本月暂无可用源数据；零值不能证明实际未使用",
    latestOnlineData: "{month} 自然月 · 最新在线数据",
    unknownCostUsers: "成本未知 {count} 人",
    queryCount: "本次查询 {count} 次",
    distributionAria: "{status} {count} 人，占可评估用户 {percent}%",
    distributionMeta: "可评估 {total} / {users} · 套餐/容量未知 {unknown}",
    accountUnknown: "未知",
    usageAria: "{name} 使用率 {percent}%",
    resultCount: "显示 {shown} / {total} 个账号",
    noCurrentMonthData: "无当月数据",
    legacyRecord: " · 旧版记录",
    historyTitle: "{month} · 截止 {cutoff}{legacy}",
    historyMeta: "生成 {time} · {users} 个账号",
    invalidServerData: "服务端返回了无法解析的数据",
    healthLoadFailed: "健康状态读取失败：{message}",
    pageLoadFailed: "页面读取失败：{message}",
    noValidSnapshot: "当前没有可展示的有效快照",
    snapshotRead: "已读取最新成功快照",
    refreshFailed: "刷新失败，继续显示最后成功快照",
    refreshCompleted: "刷新完成",
    refreshCheckFailed: "刷新状态检查失败：{message}",
    refreshCheckTimeout: "刷新状态检查超时，请稍后重新读取",
    refreshStarted: "完整刷新已在后台启动",
    refreshRequestFailed: "刷新请求失败：{message}",
    errorManualRefreshDisabled: "服务端未启用管理员同步",
    errorInvalidRefreshToken: "管理员 Token 无效",
    errorRefreshAlreadyRunning: "同步已在进行中",
    errorRefreshCooldown: "请稍后再试",
    sourceAuthoritative: "权威订阅 CSV",
    sourceIicGroup: "当前 IIC 套餐组",
    sourceLatest: "截止日用量记录",
    sourceDirectAssignment: "IIC 直接分配（套餐未知）",
  },
  "en-US": {
    pageTitle: "Kiro Credits Usage Dashboard",
    eyebrow: "KIRO ENTERPRISE · INTERNAL",
    loadingSnapshot: "Loading the latest successful snapshot…",
    reload: "Reload",
    refresh: "Sync AWS now",
    downloadCsv: "Download CSV",
    switchToEnglish: "Switch to English",
    switchToChinese: "切换为中文",
    checkingRefresh: "Checking refresh status…",
    loadingInterpretation: "Loading data interpretation…",
    dataTime: "Data times",
    browserTime: "Times are shown in your browser's local time.",
    dataCutoff: "Data cutoff",
    snapshotGenerated: "Snapshot generated",
    lastSuccessfulRefresh: "Last successful refresh",
    dataFreshness: "Data freshness",
    loadingFreshness: "Loading data freshness details…",
    overviewKicker: "OVERVIEW",
    overview: "Overview",
    overviewDescription: "Current organization resources and collection cost",
    totalUsers: "Total users",
    currentRoster: "Current subscription roster",
    totalCredits: "Cumulative Credits",
    throughLatestDataDay: "Through the latest data day",
    knownMonthlyCost: "Known monthly cost",
    athenaScanned: "Athena scanned",
    accountStatusKicker: "ACCOUNT STATUS",
    accountStatus: "Account status",
    accountStatusDescription: "Inferred from usage evidence through the data cutoff",
    active: "Active",
    unknownStatus: "Unknown status",
    usageDistributionKicker: "USAGE DISTRIBUTION",
    usageDistribution: "Usage distribution",
    statusZero: "No usage",
    statusLow: "Low usage",
    statusMedium: "Medium usage",
    statusNormal: "Normal",
    statusHigh: "High usage",
    statusUnknown: "Unknown tier/capacity",
    distributionZeroDescription: "No Credits this month · ",
    distributionLowDescription: "Nonzero and under 10% · ",
    distributionMediumDescription: "10%–<50% · ",
    distributionNormalDescription: "50%–80% · ",
    distributionHighDescription: "Over 80% · ",
    userDetails: "User details",
    loading: "Loading…",
    search: "Search",
    searchPlaceholder: "Name or email",
    status: "Status",
    allStatuses: "All statuses",
    tier: "Tier",
    allTiers: "All tiers",
    user: "User",
    email: "Email",
    creditsCapacity: "Credits / capacity",
    usageRate: "Usage",
    lastActive: "Last active",
    activeDays: "Active days",
    monthlyCost: "Monthly cost",
    tierSource: "Tier source",
    noMatchingUsers: "No users match the current filters.",
    recentSnapshots: "Recent snapshots",
    historyDescription: "The five latest valid persistent-history records, shown as summaries.",
    noHistory: "No snapshot history yet.",
    adminSync: "Administrator sync",
    refreshDialogDescription:
      "Enter an administrator token to start AWS data sync. The token is used only for this request and is not stored in the browser.",
    adminToken: "Administrator token",
    cancel: "Cancel",
    startSync: "Start sync",
    notAvailable: "N/A",
    noSnapshot: "No usable data snapshot is available. An administrator must refresh the data.",
    refreshRunning:
      "Refreshing data while showing the last successful snapshot. Last success: {time}.",
    staleSnapshot:
      "Data updates are failing while showing the last successful snapshot. Last success: {time}; consecutive failures: {failures}.",
    healthNormal: "Data service is healthy. Last successful refresh: {time}.",
    refreshEnabledTitle: "Start AWS data sync with an administrator token",
    refreshDisabledTitle: "Administrator sync is not enabled on the server",
    noMonthData: "No current-month data is available",
    noFreshnessNotice: "No data freshness details are available",
    sourceLagWarning: "Kiro source data is typically delayed by 1–2 days",
    usageCumulative: "Usage is cumulative through the data cutoff",
    usageNoCurrentMonth:
      "No current-month source data is available; zero values do not confirm non-use",
    latestOnlineData: "{month} calendar month · latest online data",
    unknownCostUsers: "Cost unknown for {count} users",
    queryCount: "{count} queries in this run",
    distributionAria: "{status}: {count} users, {percent}% of evaluable users",
    distributionMeta: "Evaluable {total} / {users} · unknown tier/capacity {unknown}",
    accountUnknown: "Unknown",
    usageAria: "{name} usage: {percent}%",
    resultCount: "Showing {shown} / {total} accounts",
    noCurrentMonthData: "No current-month data",
    legacyRecord: " · legacy record",
    historyTitle: "{month} · cutoff {cutoff}{legacy}",
    historyMeta: "Generated {time} · {users} accounts",
    invalidServerData: "The server returned data that could not be parsed",
    healthLoadFailed: "Could not load health status: {message}",
    pageLoadFailed: "Could not load the page data: {message}",
    noValidSnapshot: "There is no valid snapshot to display",
    snapshotRead: "Latest successful snapshot loaded",
    refreshFailed: "Refresh failed; continuing to show the last successful snapshot",
    refreshCompleted: "Refresh complete",
    refreshCheckFailed: "Could not check refresh status: {message}",
    refreshCheckTimeout: "Refresh status check timed out. Please reload later.",
    refreshStarted: "Full refresh started in the background",
    refreshRequestFailed: "Refresh request failed: {message}",
    errorManualRefreshDisabled: "Administrator sync is not enabled on the server",
    errorInvalidRefreshToken: "The administrator token is invalid",
    errorRefreshAlreadyRunning: "A sync is already in progress",
    errorRefreshCooldown: "Please try again later",
    sourceAuthoritative: "Authoritative subscription CSV",
    sourceIicGroup: "Current IIC tier group",
    sourceLatest: "Usage record at the data cutoff",
    sourceDirectAssignment: "Direct IIC assignment (tier unknown)",
  },
};
const STATUS = {
  zero: { labelKey: "statusZero", order: 0 },
  low: { labelKey: "statusLow", order: 1 },
  medium: { labelKey: "statusMedium", order: 2 },
  normal: { labelKey: "statusNormal", order: 3 },
  high: { labelKey: "statusHigh", order: 4 },
  unknown: { labelKey: "statusUnknown", order: 5 },
};
const DISTRIBUTION_STATUSES = ["zero", "low", "medium", "normal", "high"];
const SOURCE = {
  current_authoritative_snapshot: "sourceAuthoritative",
  current_iic_group: "sourceIicGroup",
  latest_at_data_cutoff: "sourceLatest",
  unknown_direct_assignment: "sourceDirectAssignment",
};
const ERROR_KEYS = {
  manual_refresh_disabled: "errorManualRefreshDisabled",
  invalid_refresh_token: "errorInvalidRefreshToken",
  refresh_already_running: "errorRefreshAlreadyRunning",
  refresh_cooldown: "errorRefreshCooldown",
};
const state = {
  snapshot: null,
  health: null,
  history: [],
  sort: "usage_percent",
  direction: 1,
  locale: navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US",
};
let loadGeneration = 0;
const byId = (id) => document.getElementById(id);
const text = (element, value) => {
  element.textContent = value;
};
const t = (key, values = {}) =>
  Object.entries(values).reduce(
    (message, [name, value]) => message.replaceAll(`{${name}}`, String(value)),
    MESSAGES[state.locale][key] || MESSAGES["en-US"][key] || key,
  );
const formatNumber = (value, digits = 2) =>
  value == null
    ? t("notAvailable")
    : new Intl.NumberFormat(state.locale, { maximumFractionDigits: digits }).format(value);
const formatCredit = (value) =>
  value == null
    ? t("notAvailable")
    : new Intl.NumberFormat(state.locale, { maximumFractionDigits: 0 }).format(
        Math.round(Number(value)),
      );
const formatPercent = (value) =>
  value == null ? null : Math.min(100, Math.max(0, Math.ceil(Number(value))));
const formatTimestamp = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(state.locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
};
const formatBytes = (bytes) => {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
};
const delay = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function statusLabel(status) {
  return STATUS[status] ? t(STATUS[status].labelKey) : status;
}

function sourceLabel(source) {
  return SOURCE[source] ? t(SOURCE[source]) : source;
}

function errorMessage(error) {
  const key = ERROR_KEYS[error?.payload?.error];
  return key ? t(key) : error?.message || "";
}

function localizeServerText(value, fallbackKey) {
  const normalized = String(value || "");
  const keys = {
    "Kiro 源数据通常存在 1–2 天延迟": "sourceLagWarning",
    "Usage is cumulative through data_cutoff": "usageCumulative",
    用量累计至数据截止日: "usageCumulative",
    "No current-month source data is available; zero values are not confirmed non-use":
      "usageNoCurrentMonth",
    "本月暂无可用源数据；零值不能证明实际未使用": "usageNoCurrentMonth",
  };
  return keys[normalized] ? t(keys[normalized]) : normalized || t(fallbackKey);
}

function toast(message) {
  const element = byId("toast");
  text(element, message);
  element.classList.add("show");
  window.setTimeout(() => element.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  const raw = await response.text();
  let payload;
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch {
    throw new Error(response.ok ? t("invalidServerData") : `HTTP ${response.status}`);
  }
  if (!response.ok) {
    const error = new Error(payload.message || payload.error || `HTTP ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function updateLanguageToggle() {
  const button = byId("languageToggle");
  const label = state.locale === "zh-CN" ? t("switchToEnglish") : t("switchToChinese");
  button.setAttribute("aria-label", label);
  button.title = label;
}

function applyLocale() {
  document.documentElement.lang = state.locale;
  document.title = t("pageTitle");
  document
    .querySelectorAll("[data-i18n]")
    .forEach((element) => text(element, t(element.dataset.i18n)));
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  updateLanguageToggle();
  updateSortIndicators();
  if (state.health) renderHealth();
  if (state.snapshot) {
    renderSummary();
    renderTable();
  }
  renderHistory();
}

function updateRefreshControl() {
  const button = byId("refresh");
  const enabled = Boolean(state.health?.manual_refresh_enabled);
  button.disabled =
    !enabled || state.health?.manual_refresh_running || state.health?.status === "refreshing";
  button.title = t(enabled ? "refreshEnabledTitle" : "refreshDisabledTitle");
}

function renderHealth() {
  const health = state.health;
  const banner = byId("healthBanner");
  banner.className = "health";
  text(byId("timeLastSuccess"), formatTimestamp(health?.last_success_at));
  if (!health || !health.has_snapshot) {
    banner.classList.add("error");
    text(banner, t("noSnapshot"));
    updateRefreshControl();
    return;
  }
  if (health.manual_refresh_running || health.status === "refreshing") {
    banner.classList.add("loading");
    text(banner, t("refreshRunning", { time: formatTimestamp(health.last_success_at) }));
  } else if (health.serving_stale_snapshot || health.status === "error") {
    banner.classList.add("stale");
    text(
      banner,
      t("staleSnapshot", {
        time: formatTimestamp(health.last_success_at),
        failures: health.consecutive_failures,
      }),
    );
  } else {
    text(banner, t("healthNormal", { time: formatTimestamp(health.last_success_at) }));
  }
  updateRefreshControl();
}

function renderSummary() {
  const snapshot = state.snapshot;
  if (!snapshot) return;
  const summary = snapshot.summary;
  const cutoff = snapshot.data_cutoff || t("noMonthData");
  const lagWarning = localizeServerText(snapshot.source_lag_warning, "noFreshnessNotice");
  text(byId("subtitle"), t("latestOnlineData", { month: snapshot.month }));
  text(byId("timeCutoff"), cutoff);
  text(byId("timeGenerated"), formatTimestamp(snapshot.generated_at));
  text(byId("timeDelay"), lagWarning);
  text(byId("kpiUsers"), summary.users);
  text(byId("kpiZero"), summary.zero);
  text(byId("kpiLow"), summary.low);
  text(byId("kpiMedium"), summary.medium);
  text(byId("kpiNormal"), summary.normal);
  text(byId("kpiHigh"), summary.high ?? 0);
  renderAccountSummary(snapshot.users);
  renderDistribution(summary);
  text(byId("kpiCredits"), formatCredit(summary.total_credits));
  text(byId("kpiCost"), `$${formatNumber(summary.known_monthly_cost_usd)}`);
  text(byId("kpiUnknownCost"), t("unknownCostUsers", { count: summary.unknown_cost_users }));
  text(byId("kpiScan"), formatBytes(snapshot.collection?.data_scanned_bytes));
  text(byId("kpiQueries"), t("queryCount", { count: snapshot.collection?.query_count ?? "—" }));

  const notice = byId("dataNotice");
  notice.className = snapshot.no_month_data ? "data-notice warning" : "data-notice";
  text(notice, localizeServerText(snapshot.usage_interpretation, "loadingInterpretation"));
  text(byId("footerMeta"), `${t("dataCutoff")} ${cutoff} · ${lagWarning}`);
  populateTiers(snapshot.users);
}

function inferredAccountStatus(user) {
  const hasUsageEvidence =
    Number(user.credits) > 0 ||
    Number(user.active_days) > 0 ||
    Boolean(user.first_active) ||
    Boolean(user.last_active);
  return hasUsageEvidence ? "active" : "unknown";
}

function renderAccountSummary(users) {
  const active = users.filter((user) => inferredAccountStatus(user) === "active").length;
  text(byId("subscriptionActive"), active);
  text(byId("subscriptionUnknown"), users.length - active);
}

function renderDistribution(summary) {
  const total = DISTRIBUTION_STATUSES.reduce(
    (sum, status) => sum + Number(summary[status] || 0),
    0,
  );
  const maximum = Math.max(total, 1);
  DISTRIBUTION_STATUSES.forEach((status) => {
    const count = Number(summary[status] || 0);
    const suffix = status.charAt(0).toUpperCase() + status.slice(1);
    const meter = byId(`distribution${suffix}`);
    const percent = total > 0 ? Math.round((count / total) * 100) : 0;
    meter.max = maximum;
    meter.value = count;
    meter.setAttribute(
      "aria-label",
      t("distributionAria", { status: statusLabel(status), count, percent }),
    );
    text(byId(`distribution${suffix}Percent`), `${percent}%`);
  });
  text(
    byId("distributionMeta"),
    t("distributionMeta", { total, users: summary.users, unknown: summary.unknown || 0 }),
  );
}

function populateTiers(users) {
  const select = byId("tierFilter");
  const current = select.value;
  const tiers = [...new Set(users.map((user) => user.tier))].sort();
  select.replaceChildren(new Option(t("allTiers"), ""));
  tiers.forEach((tier) => select.add(new Option(tier, tier)));
  if (tiers.includes(current)) select.value = current;
}

function compare(a, b) {
  const key = state.sort;
  let left = a[key];
  let right = b[key];
  if (key === "usage_percent") {
    left = a.capacity > 0 ? (Number(a.credits) * 100) / Number(a.capacity) : null;
    right = b.capacity > 0 ? (Number(b.credits) * 100) / Number(b.capacity) : null;
  }
  if (key === "status") {
    left = STATUS[a.status]?.order ?? 99;
    right = STATUS[b.status]?.order ?? 99;
  }
  if (key === "last_active") {
    left = left || null;
    right = right || null;
  }
  if (left == null || right == null) {
    if (left == null && right == null) return a.email.localeCompare(b.email, state.locale);
    return left == null ? 1 : -1;
  }
  const result =
    typeof left === "string"
      ? left.localeCompare(right, state.locale)
      : Number(left) - Number(right);
  return result * state.direction || a.email.localeCompare(b.email, state.locale);
}

function filteredUsers() {
  if (!state.snapshot) return [];
  const query = byId("search").value.trim().toLocaleLowerCase(state.locale);
  const status = byId("statusFilter").value;
  const tier = byId("tierFilter").value;
  return state.snapshot.users
    .filter(
      (user) =>
        !query || `${user.user_name} ${user.email}`.toLocaleLowerCase(state.locale).includes(query),
    )
    .filter((user) => !status || user.status === status)
    .filter((user) => !tier || user.tier === tier)
    .sort(compare);
}

function cell(value, className = "") {
  const td = document.createElement("td");
  td.className = className;
  text(td, value);
  return td;
}

function renderTable() {
  const users = filteredUsers();
  const body = byId("userRows");
  body.replaceChildren();
  users.forEach((user) => {
    const row = document.createElement("tr");
    row.append(cell(user.user_name, "user"));
    row.append(cell(user.email || "—", "email"));
    const accountCell = document.createElement("td");
    const accountBadge = document.createElement("span");
    const accountStatus = inferredAccountStatus(user);
    accountBadge.className = `badge account-${accountStatus}`;
    text(accountBadge, accountStatus === "active" ? t("active") : t("accountUnknown"));
    accountCell.append(accountBadge);
    row.append(accountCell);
    row.append(cell(user.tier));
    const capacity = user.capacity > 0 ? formatCredit(user.capacity) : t("notAvailable");
    row.append(cell(`${formatCredit(user.credits)} / ${capacity}`));

    const usageCell = document.createElement("td");
    usageCell.className = "usage";
    const line = document.createElement("div");
    line.className = "usage-line";
    const rawPercent =
      user.capacity > 0 ? (Number(user.credits) * 100) / Number(user.capacity) : null;
    const displayPercent = formatPercent(rawPercent);
    text(line, displayPercent == null ? t("notAvailable") : `${displayPercent}%`);
    usageCell.append(line);
    if (displayPercent != null) {
      const progress = document.createElement("progress");
      progress.className = user.status;
      progress.max = 100;
      progress.value = displayPercent;
      progress.setAttribute(
        "aria-label",
        t("usageAria", { name: user.user_name, percent: displayPercent }),
      );
      usageCell.append(progress);
    }
    row.append(usageCell);

    row.append(cell(user.last_active || "—"));
    row.append(cell(user.active_days));
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge ${user.status}`;
    text(badge, statusLabel(user.status));
    statusCell.append(badge);
    row.append(statusCell);
    row.append(
      cell(
        user.monthly_cost_usd == null
          ? t("notAvailable")
          : `$${formatNumber(user.monthly_cost_usd)}`,
      ),
    );
    row.append(cell(sourceLabel(user.tier_source)));
    body.append(row);
  });
  text(
    byId("resultCount"),
    t("resultCount", { shown: users.length, total: state.snapshot?.users.length || 0 }),
  );
  byId("empty").hidden = users.length !== 0;
}

function renderHistory() {
  const list = byId("historyList");
  list.replaceChildren();
  const entries = state.history.slice(0, 5);
  entries.forEach((entry) => {
    const item = document.createElement("li");
    const main = document.createElement("div");
    const title = document.createElement("strong");
    const cutoff = entry.data_cutoff || t("noCurrentMonthData");
    const legacy = entry.legacy ? t("legacyRecord") : "";
    text(title, t("historyTitle", { month: entry.month, cutoff, legacy }));
    const meta = document.createElement("span");
    text(
      meta,
      t("historyMeta", {
        time: formatTimestamp(entry.generated_at),
        users: entry.summary?.users ?? "—",
      }),
    );
    main.append(title, meta);
    const hash = document.createElement("code");
    text(hash, entry.content_hash ? entry.content_hash.slice(0, 8) : "—");
    item.append(main, hash);
    list.append(item);
  });
  byId("historyEmpty").hidden = entries.length !== 0;
}

async function loadAll(showToast = false, reload = false) {
  const requestGeneration = ++loadGeneration;
  const reloadButton = byId("reload");
  reloadButton.disabled = true;
  try {
    const currentRequest = reload ? api("/api/reload", { method: "POST" }) : api("/api/current");
    const results = await Promise.allSettled([
      currentRequest,
      api("/api/health"),
      api("/api/history"),
    ]);
    if (requestGeneration !== loadGeneration) return;

    const [snapshotResult, healthResult, historyResult] = results;
    if (healthResult.status === "fulfilled") {
      state.health = healthResult.value;
      renderHealth();
    } else {
      const banner = byId("healthBanner");
      banner.className = "health error";
      text(banner, t("healthLoadFailed", { message: errorMessage(healthResult.reason) }));
    }
    if (snapshotResult.status === "fulfilled") {
      state.snapshot = snapshotResult.value;
      renderSummary();
      renderTable();
      if (showToast) toast(t("snapshotRead"));
    } else {
      state.snapshot = null;
      text(byId("subtitle"), t("noValidSnapshot"));
      if (healthResult.status !== "fulfilled") {
        const banner = byId("healthBanner");
        banner.className = "health error";
        text(banner, t("pageLoadFailed", { message: errorMessage(snapshotResult.reason) }));
      }
    }
    if (historyResult.status === "fulfilled") {
      state.history = historyResult.value.entries || [];
      renderHistory();
    }
  } finally {
    if (requestGeneration === loadGeneration) {
      reloadButton.disabled = false;
      updateRefreshControl();
    }
  }
}

async function waitForRefresh() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    await delay(3000);
    try {
      const health = await api("/api/health");
      state.health = health;
      renderHealth();
      if (health.manual_refresh_running || health.status === "refreshing") continue;
      await loadAll(false, true);
      toast(health.status === "error" ? t("refreshFailed") : t("refreshCompleted"));
      return;
    } catch (error) {
      if (attempt === 99) toast(t("refreshCheckFailed", { message: errorMessage(error) }));
    }
  }
  toast(t("refreshCheckTimeout"));
}

function clearRefreshToken() {
  byId("refreshToken").value = "";
}

function closeRefreshDialog() {
  const dialog = byId("refreshDialog");
  clearRefreshToken();
  if (dialog.open && typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
  dialog.hidden = true;
}

function openRefreshDialog() {
  const dialog = byId("refreshDialog");
  dialog.hidden = false;
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  byId("refreshToken").focus();
}

async function submitRefresh(event) {
  event.preventDefault();
  const tokenInput = byId("refreshToken");
  const token = tokenInput.value;
  if (!token) return;
  clearRefreshToken();
  closeRefreshDialog();
  const button = byId("refresh");
  button.disabled = true;
  try {
    await api("/api/refresh", { method: "POST", headers: { "X-Refresh-Token": token } });
    toast(t("refreshStarted"));
    void waitForRefresh();
  } catch (error) {
    toast(t("refreshRequestFailed", { message: errorMessage(error) }));
    updateRefreshControl();
  } finally {
    clearRefreshToken();
  }
}

byId("languageToggle").addEventListener("click", () => {
  state.locale = state.locale === "zh-CN" ? "en-US" : "zh-CN";
  applyLocale();
});
byId("reload").addEventListener("click", () => loadAll(true, true));
byId("refresh").addEventListener("click", openRefreshDialog);
byId("refreshForm").addEventListener("submit", submitRefresh);
byId("refreshCancel").addEventListener("click", closeRefreshDialog);
byId("refreshDialog").addEventListener("cancel", clearRefreshToken);
byId("refreshDialog").addEventListener("close", clearRefreshToken);
[byId("search"), byId("statusFilter"), byId("tierFilter")].forEach((element) => {
  element.addEventListener("input", renderTable);
  element.addEventListener("change", renderTable);
});
function updateSortIndicators() {
  document.querySelectorAll("th button[data-sort]").forEach((button) => {
    const active = button.dataset.sort === state.sort;
    button.parentElement.setAttribute(
      "aria-sort",
      active ? (state.direction === 1 ? "ascending" : "descending") : "none",
    );
  });
}

document.querySelectorAll("th button[data-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.sort;
    if (state.sort === key) state.direction *= -1;
    else {
      state.sort = key;
      state.direction = 1;
    }
    updateSortIndicators();
    renderTable();
  });
});

applyLocale();
loadAll();
window.setInterval(() => loadAll(false), 60_000);
