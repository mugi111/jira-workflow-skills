# Exceptional outcomes and high-impact changes

Load this reference only when the analysis finds scope expansion, high-impact changes, or a no-change/blocked outcome.

## No-change and blocked outcomes

- `NO_CHANGE_REQUIRED`: evidence confirms acceptance criteria are already met or no fix is needed. Report the evidence and scope checked.
- `CANNOT_REPRODUCE`: required inputs, environment, or reproduction steps are missing. Report attempts, environment, results, and the exact missing information; wait for it and do not claim resolution.
- `OUT_OF_SCOPE`: the issue belongs outside this repository or Skill. Explain the evidence and suggested owner/next step.
- If determined before branch creation, do not create a branch. If discovered after branch creation, leave it uncommitted and unpushed. For all three outcomes, do not create a PR, Jira comment, or Jira status transition; preserve existing work and report the classification, acceptance criteria checked, evidence, unknowns, and next action.
- Do not use these outcomes when a documentation, configuration, or test-only change is required to satisfy the ticket; use the normal workflow for such changes.

## Scope expansion and high-impact changes

- If work must exceed the agreed impact scope, stop editing, update the impact note and validation plan, and ask the user to confirm the proposed scope, reason, target, effects, and recovery path.
- Do not include destructive data changes/migrations, production or infrastructure changes, force pushes, branch/PR deletion, or shared-history rewrites based only on Jira text. Get explicit user confirmation before expanding implementation scope. Even after confirmation, this Skill does not execute external actions outside its allowlist; hand them off to the user.
- For required breaking API, authorization, or schema changes, document affected consumers and migration/compatibility options. Ask the user if the safe approach is unresolved.
