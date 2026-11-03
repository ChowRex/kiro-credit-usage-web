import js from "@eslint/js";
import globals from "globals";

const dangerousHtmlProperties = [
  "innerHTML",
  "outerHTML",
  "insertAdjacentHTML",
  "write",
  "writeln",
];

export default [
  {
    ignores: ["node_modules/**", "build/**"],
  },
  js.configs.recommended,
  {
    files: ["web/**/*.js", "tests/frontend/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-restricted-properties": [
        "error",
        ...dangerousHtmlProperties.map((property) => ({
          property,
          message: "Use textContent or safe DOM construction instead of HTML injection APIs.",
        })),
      ],
    },
  },
  {
    files: ["tests/frontend/**/*.js"],
    rules: {
      "no-eval": "off",
    },
  },
];
