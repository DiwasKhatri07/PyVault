# PyVaultRCE 2.5.0

This release includes:

- Encrypted persistent Python sessions with owner/admin controls.
- Short public links that expose metadata only; source remains private.
- Public usernames and profiles with tags, descriptions, comments, deduplicated views, and verification badges.
- Rate-limited comments and escaped template rendering.
- PyVaultRCE and compatibility `codemanager` clients defaulting to the hosted deployment.
- Short-lived subprocess execution by default with a clean environment, temporary directory, timeout, CPU/file limits, and a practical memory ceiling.
- A schema reference without any live session or admin-token data.

The subprocess boundary is defense-in-depth, not a complete VM/container sandbox. Use a dedicated isolated worker for hostile multi-tenant code.
