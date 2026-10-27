# Local validation

Depot automation was retired by the owner on 2026-10-26 (JCK-2596, incident JCK-2555). No workflows in this directory are discovered by Depot or GitHub Actions.

Use the repository's existing build, lint and test entry points documented in AGENTS.md and README. Run checks locally with bounded workers and process timeouts. Validate affected changes first and broaden checks when warranted; do not start a full remote suite for every commit or push.

`local-reference/` preserves the former workflow recipes byte-for-byte so check coverage, setup requirements, services, working directories, environment inputs and matrices remain reviewable. These YAML files are reference material, not a local workflow runner. Translate setup actions and resolve matrix/event inputs before manually running a recipe. Do not execute Depot setup/build/cache actions or upload artifacts to Depot; use local tools and caches. Never substitute synthetic success for checks that were not run.

The GitHub app was disconnected and a Depot organization CI cap applied separately. Depot-specific required checks must be retired through the reviewed migration; unrelated checks/review controls remain in force. This change does not delete provider billing evidence, caches or existing runtime deployments.
