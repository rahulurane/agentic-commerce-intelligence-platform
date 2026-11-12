// Flat ESLint config (ESLint 9) for the ACIP demo UI. Kept dependency-light: it uses
// only the pinned typescript-eslint + react-hooks/react-refresh plugins (no @eslint/js)
// so the lint gate runs with exactly the deps declared in package.json.
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  {
    ignores: ["dist", "node_modules"],
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 2020,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        window: "readonly",
        document: "readonly",
        console: "readonly",
        fetch: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        HTMLInputElement: "readonly",
        HTMLSelectElement: "readonly",
        HTMLFormElement: "readonly",
        HTMLElement: "readonly",
        HTMLDivElement: "readonly",
        HTMLButtonElement: "readonly",
        KeyboardEvent: "readonly",
        MouseEvent: "readonly",
        Node: "readonly",
        localStorage: "readonly",
        navigator: "readonly",
        performance: "readonly",
        AbortController: "readonly",
        requestAnimationFrame: "readonly",
        cancelAnimationFrame: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        getComputedStyle: "readonly",
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
];
