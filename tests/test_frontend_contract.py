"""Static frontend contract tests."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    """Verify required dashboard markup, behavior, safety, and i18n constraints."""

    def test_fixed_shell_has_required_controls_and_safe_dom_rendering(self) -> None:
        """Require dashboard controls and safe DOM rendering primitives."""
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        for element_id in (
            "languageToggle",
            "healthBanner",
            "reload",
            "refresh",
            "search",
            "statusFilter",
            "tierFilter",
            "userRows",
            "kpiUsers",
            "kpiZero",
            "kpiLow",
            "kpiHigh",
            "dataNotice",
            "timeCutoff",
            "timeGenerated",
            "timeLastSuccess",
            "timeDelay",
            "historyList",
            "historyEmpty",
            "subscriptionActive",
            "subscriptionUnknown",
            "distributionMeta",
            "distributionZero",
            "distributionLow",
            "distributionMedium",
            "distributionNormal",
            "distributionHigh",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('aria-label="切换为 English"', html)
        self.assertIn("<svg", html)
        self.assertIn('data-i18n="pageTitle"', html)
        self.assertIn('data-i18n-placeholder="searchPlaceholder"', html)
        self.assertIn("/api/export.csv", html)
        self.assertIn("/api/current", script)
        self.assertIn("/api/health", script)
        self.assertIn("/api/history", script)
        self.assertIn("/api/reload", script)
        self.assertIn("/api/refresh", script)
        self.assertIn("usage_interpretation", script)
        self.assertIn("manual_refresh_enabled", script)
        self.assertIn("manual_refresh_running", script)
        self.assertIn("X-Refresh-Token", script)
        self.assertIn('sort: "usage_percent"', script)
        self.assertIn("direction: 1", script)
        self.assertIn("navigator.language", script)
        self.assertIn('"zh-CN"', script)
        self.assertIn('"en-US"', script)
        self.assertIn("document.documentElement.lang", script)
        self.assertIn("updateLanguageToggle", script)
        self.assertIn("Math.ceil", script)
        self.assertIn("Math.min(100", script)
        self.assertIn("new Intl.DateTimeFormat(state.locale", script)
        self.assertNotIn("timeZoneName", script)
        self.assertIn('class="overview-grid"', html)
        self.assertIn('class="distribution-panel"', html)
        self.assertIn("meter.max = maximum", script)
        self.assertIn("meter.value = count", script)
        self.assertIn("inferredAccountStatus", script)
        self.assertIn('unknownStatus: "未知状态"', script)
        self.assertNotIn('id="subscriptionPending"', html)
        self.assertIn("updateSortIndicators", script)
        self.assertIn('setAttribute("aria-label"', script)
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("localStorage", script)
        self.assertNotIn(".style.", script)
        self.assertIn('document.createElement("progress")', script)
        self.assertNotIn('fetch("http://', script)
        self.assertNotIn('fetch("https://', script)
        self.assertNotIn("<style", html)
        self.assertNotIn("style=", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn('class="brand"', html)
        self.assertIn("grid-template-rows: 1rem 2.4rem 1.25rem", styles)
        self.assertIn("grid-template-rows: 1rem 4.8rem 1.25rem", styles)
        self.assertIn("scrollbar-gutter: stable", styles)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 30rem", styles)
        self.assertIn("grid-template-columns: 38px repeat(3, minmax(0, 1fr))", styles)
        self.assertIn(".actions .language-toggle", styles)
        self.assertIn("font-synthesis: none", styles)
        self.assertIn("white-space: nowrap", styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", styles)
        self.assertIn("@media (max-width: 680px)", styles)
        self.assertNotIn('content="light dark"', html)
        self.assertNotIn("prefers-color-scheme: dark", styles)
        self.assertIn("prefers-reduced-motion: reduce", styles)


if __name__ == "__main__":
    unittest.main()
