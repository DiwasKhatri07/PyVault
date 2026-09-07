# Architecture notes

PyVault has two independently useful parts: a Flask web/API service and the `PyVaultRCE` Python client.

## Request flow

1. A user submits Python code through the web editor or `CodeManager.enc`.
2. The server validates the payload, creates a random session identifier, and stores code plus metadata in SQLite.
3. The client receives the session ID and can request metadata or fetch the code for execution.
4. Administrative edits and deletion require authorization through the admin token or owner token flow.

## Storage

SQLite keeps the default deployment simple and portable. Runtime state must be backed up using the operator's normal deployment process; it should not be committed to Git. For higher concurrency or multi-instance deployments, a database abstraction and shared storage strategy should be introduced before scaling out.

## Execution boundary

The client runner writes fetched code to a temporary directory and invokes Python in isolated mode with a clean environment, a timeout, and POSIX resource limits where available. This is defense in depth only. It does not replace containerization, a VM boundary, or a network/filesystem policy for hostile code.

## Extension points

Future changes should preserve strict session-ID validation, avoid putting credentials in URLs, keep metadata reads separate from execution-counting fetches, and make authorization requirements explicit in both server and client documentation.
