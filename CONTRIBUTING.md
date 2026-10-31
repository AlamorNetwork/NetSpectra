# Contributing

Start with README.md and docs/ROADMAP_TODO.md. Work on one bounded issue with
acceptance criteria before implementation. Use stable IDs such as
PPRL-M01-W01-T01 and TODO / IN_PROGRESS / BLOCKED / REVIEW / DONE.

1. Branch from main using feat/<description> or fix/<description>.
2. Use Conventional Commits: feat:, fix:, docs:, test:, build:, ci:, chore:.
3. Run the README verification commands and record exact evidence.
4. Open a PR using the template; request review before merging.

Use synthetic data by default. Do not commit secrets, private identifiers,
payloads, captures or generated research artifacts. Report limitations and
negative results. Code is Apache-2.0; documentation is CC BY 4.0; datasets
require separate, explicit terms and provenance.

## GitHub branch protection (administrator setup)

After creating a GitHub repository and running CI once, configure a ruleset
targeting main: require a pull request, one approving review, dismissal of stale
approvals, resolved conversations, and passing status checks
`smoke (ubuntu-latest)` and `smoke (windows-latest)`. Block force pushes and
branch deletion; avoid bypass permissions. Verify the displayed check names
against the first CI run before selecting them.

These are setup instructions, not an applied remote rule. This local starter
has no remote repository, so enforcement and hosted CI remain pending.
