import { defineConfig, globalIgnores } from "eslint/config";
import eslint from "@eslint/js";
import next from "@next/eslint-plugin-next";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const eslintConfig = defineConfig([
  globalIgnores([
    ".next/**",
    "dist/**",
    "out/**",
    "build/**",
    "work/**",
    ".test-tmp/**",
    ".artifacts/**",
    "tmp/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    "backend/.venv/**",
    "backend/.artifacts/**",
    "backend/.pytest-tmp/**",
    "backend/.mypy_cache/**",
    "backend/.pytest_cache/**",
    "backend/.ruff_cache/**",
    "next-env.d.ts",
  ]),
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.ts", "**/*.tsx", "**/*.mts"],
    extends: [tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // JSON/API 边界用显式断言收窄 any/unknown 是本项目既定模式：
      // no-unnecessary-type-assertion 会误判这类断言且其 autofix 会破坏类型，unsafe 家族与之同源，一并关闭。
      "@typescript-eslint/no-unnecessary-type-assertion": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-call": "off",
      "@typescript-eslint/no-unsafe-argument": "off",
    },
  },
  react.configs.flat.recommended,
  react.configs.flat["jsx-runtime"],
  reactHooks.configs.flat["recommended-latest"],
  jsxA11y.flatConfigs.recommended,
  next.configs["core-web-vitals"],
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.serviceworker,
      },
    },
    settings: {
      react: {
        version: "detect",
      },
    },
    rules: {
      // Named scroll regions must be keyboard-focusable so overflow content can be reached.
      "jsx-a11y/no-noninteractive-tabindex": [
        "error",
        { tags: ["section"], roles: ["tabpanel", "region"] },
      ],
    },
  },
]);

export default eslintConfig;
