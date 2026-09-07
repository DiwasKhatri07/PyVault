# Security Policy

## Scope

This policy covers the PyVault server, the `PyVaultRCE` client, and the repository configuration. The public demo is shared infrastructure and is not a suitable place for sensitive code or secrets.

## Supported versions

| Version | Status |
| --- | --- |
| 2.5.x | Current |
| Older releases | Best effort only |

## Reporting a vulnerability

Please do not open a public issue for an undisclosed vulnerability. Contact the maintainer privately through [@DiwasKhatri07](https://github.com/DiwasKhatri07) with a clear description, affected version, reproduction steps, impact, and a suggested mitigation if available.

Allow reasonable time for triage and remediation before public disclosure. Do not access, alter, or exfiltrate data belonging to other users during research.

## Deployment guidance

Use a strong `SESSION_SECRET`, protect admin credentials, keep the SQLite database out of version control, restrict network access where possible, and place untrusted execution behind dedicated container or VM isolation. Session IDs and owner tokens must be treated as secrets.
