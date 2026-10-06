# Security policy

Prism processes employee communication and stores delegated Microsoft credentials. Treat a
suspected vulnerability as sensitive even when no credential is visible.

## Supported versions

Prism has not made its first stable release. Security fixes currently target the latest commit
on `main`. A supported-version table will be added when tagged releases begin.

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting for this repository:

<https://github.com/oneclarity-ai/prism/security/advisories/new>

Include:

- affected commit or version;
- impact and the security boundary involved;
- reproducible steps or a minimal proof of concept;
- whether credentials, messages, or tenant data may have been exposed;
- any suggested mitigation.

Do not access data that is not yours, send messages to real employees, degrade a service, or
publish details before maintainers have had a reasonable opportunity to respond. The project
does not currently promise a response-time SLA, but reports will be acknowledged and triaged as
maintainer capacity allows.

## Deployment responsibilities

- Use HTTPS and a strong `OPERATOR_API_TOKEN` outside local development.
- Store `.env`, the Fernet key, Microsoft secrets, and Azure keys in a managed secret store.
- Restrict database access and encrypt backups; they may contain employee conversations.
- Use an isolated Entra app and grant only the documented delegated permissions.
- Enable automation only for explicitly selected people who are appropriate recipients.
- Run the scheduler in one process only.
- Put public endpoints behind request-size limits, rate limiting, and monitoring.
- Rotate a credential immediately if it enters Git history, logs, an issue, or a pull request.

Changing `MICROSOFT_TOKEN_ENCRYPTION_KEY` does not re-encrypt stored tokens. Reconnect the
Microsoft account after an intentional key rotation.

## Known limitations

- Prism has not had an independent security audit.
- The operator token is a single shared control-plane secret, not user-level RBAC.
- The in-process scheduler and background tasks are intended for a single-instance deployment.
- Application-level rate limiting and request-body limits are expected from the deployment edge.
