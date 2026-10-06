# Roadmap

Prism is pre-release. The roadmap prioritizes safe operation and contributor confidence over a
broad feature surface.

## Before v0.1.0

- Select an open-source licence after confirming copyright ownership.
- Complete history cleanup for organization-specific material from the pre-public commit.
- Validate a fresh Docker install and the full PostgreSQL integration suite in CI.
- Add explicit configuration validation for every production-required setting.
- Expand mypy coverage from core models and schemas into services and route adapters.
- Document one supported production deployment with HTTPS and external secret management.

## After v0.1.0

- Separate scheduler/worker execution from the API for multi-replica deployments.
- Add configurable data-retention and deletion workflows.
- Add operator identity and role-based authorization beyond a shared token.
- Improve webhook rate limiting, observability, and durable job recovery.
- Expand provider-independent LLM and embedding interfaces where justified by real deployments.

Roadmap items are directional, not commitments. Propose substantial changes in an issue before
implementation so maintainers can confirm scope and security implications.
