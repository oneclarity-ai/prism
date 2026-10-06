# Changelog

All notable changes to Prism will be documented in this file.

The project intends to follow [Semantic Versioning](https://semver.org/) after its first tagged
release. Dates use ISO 8601.

## [Unreleased]

### Added

- Open-source repository documentation, contributor guidance, security policy, and support policy.
- Docker and Compose development path.
- Ruff, mypy, dependency auditing, and tracked-file secret scanning commands.
- GitHub issue/PR templates, CI, security workflows, and Dependabot configuration.

### Changed

- Generalized organization- and manager-specific runtime names under the Prism identity.
- Production and publicly exposed API configurations now fail closed without an operator token.

### Security

- Replaced organization-specific example configuration with safe placeholders.
- Documented delegated-token, webhook, scheduler, and database security boundaries.
- Updated vulnerable runtime and test dependencies identified by `pip-audit`.
