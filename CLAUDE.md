<!-- BEGIN OWNER LOCAL CI OVERRIDE JCK-2596 -->
## Local-only validation — owner decision 2026-10-26

Depot is retired across these repositories (JCK-2596, incident JCK-2555). This supersedes older Depot-specific CI, merge-gate, cache, registry and pre-push guidance in this file or inherited skills. Run existing build/lint/test commands locally with bounded concurrency and process timeouts. Never invoke paid Depot compute or reconnect it. Do not automatically run a full suite per commit/push; preserve coverage and validate changes proportionately. Retain unrelated review and security requirements. Former workflow recipes in `.ci/local-reference/` are inert local setup/check references, not executable automation or proof of passing tests.
<!-- END OWNER LOCAL CI OVERRIDE JCK-2596 -->

# Claude Code instructions

All agent instructions live in `AGENTS.md`; follow them exactly.

@AGENTS.md
