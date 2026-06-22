// commitlint.config.js — Conventional Commits enforcement for ComfyUI-Pack-Of-ThatAIGod
//
// This config enforces the Conventional Commits specification:
//   <type>[optional scope]: <description>
//
// For development workflow, install:
//   npm install -g @commitlint/cli @commitlint/config-conventional
//
// Then enable with:
//   npx husky install  (or manually add a commit-msg hook)

"use strict";

module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    // Enforce valid commit types used in this project
    "type-enum": [
      2,
      "always",
      [
        "feat",     // A new feature
        "fix",      // A bug fix
        "docs",     // Documentation only changes
        "style",    // Changes that do not affect the meaning of the code
        "refactor", // A code change that neither fixes a bug nor adds a feature
        "perf",     // A code change that improves performance
        "test",     // Adding missing tests or correcting existing tests
        "build",    // Changes that affect the build system or external dependencies
        "ci",       // Changes to CI configuration files and scripts
        "chore",    // Other changes that don't modify src or test files
        "revert",   // Reverts a previous commit
        "release",  // A release commit (version bump + changelog)
      ],
    ],
    // Scope must be lowercase and use kebab-case when provided
    "scope-case": [2, "always", "lower-case"],
    // Subject must not be empty and must not end with a period
    "subject-empty": [2, "never"],
    "subject-full-stop": [2, "never", "."],
    // Header max length
    "header-max-length": [2, "always", 100],
  },
  // Custom help message shown on validation failure
  helpUrl:
    "https://www.conventionalcommits.org/en/v1.0.0/\n" +
    "Valid types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert, release\n" +
    "Format: <type>(<scope>): <subject>\n" +
    "Example: feat(LLM_Node): add streaming response for vision models\n",
};
