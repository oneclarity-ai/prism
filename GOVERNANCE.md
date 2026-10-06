# Governance

Prism currently uses a lightweight maintainer-led governance model appropriate for a pre-release
project.

## Roles

- **Contributors** propose issues, documentation, tests, and code changes.
- **Maintainers** triage issues, review changes, manage releases, handle security reports, and
  protect the project's safety and architectural boundaries.

The GitHub organization controls maintainer access. A public maintainer list and succession policy
should be added if the maintainer group grows beyond the founding team.

## Decisions

Routine changes are decided through pull-request review. Large changes—especially authorization,
message sending, data retention, external providers, or schema compatibility—should begin with a
public design issue unless they contain security-sensitive information.

Maintainers seek rough consensus, but may decline changes that expand operational or security
burden beyond current capacity. Security fixes may be developed privately and disclosed after a
patch is available.

## Releases and compatibility

Prism plans to use Semantic Versioning after the first tagged release. Before `1.0.0`, minor
versions may contain documented breaking changes. Deprecations should identify a replacement and,
when practical, remain for at least one minor release before removal.

Release notes are derived from `CHANGELOG.md`. Releases require passing CI, a migration review,
and confirmation that examples and generated API documentation still match behavior.

## Branches and review

`main` is the integration branch and should remain releasable. Work happens on short-lived branches
through pull requests. At least one maintainer approval is expected; sensitive changes may require
a second reviewer. Squash merge is the preferred merge strategy.
