# PyVault Wiki

## Project overview

PyVault combines a Flask service with the `PyVaultRCE` client. The service provides the web editor, session API, metadata views, and protected administration. The client provides the Python-first upload and execution workflow.

## First session

Install `PyVaultRCE`, set `PYVAULT_URL`, and call `CodeManager.enc("script.py")`. Save the returned session ID as a secret. Call `CodeManager.info(session_id)` for metadata or `CodeManager.run(session_id)` to execute trusted code.

## Metadata and sharing

Labels, usernames, descriptions, tags, and declared library names are metadata. They improve discovery and presentation but do not install dependencies or grant access to source code. Treat a session ID as a bearer capability.

## Local operations

The server creates its SQLite database in the application directory. Use a process manager and a production WSGI server for deployment, rotate secrets through environment variables, and restrict the admin surface at the network layer.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Connection refused | Confirm the server is running and `PYVAULT_URL` is set correctly. |
| Invalid session ID | Use the exact lowercase hexadecimal ID returned by the upload call. |
| Missing dependency | Install the dependency in the environment that performs execution; metadata does not install packages. |
| Admin access fails | Verify the token and `SESSION_SECRET`; never put the admin token in a URL. |
| Execution times out | Reduce workload or increase the configured timeout only for trusted code. |

## Versioning

The published Python client currently targets the 2.5.x line. Keep server and client changes backwards-compatible where practical, and document endpoint or metadata changes in the root README.

## Further reading

- [Architecture](ARCHITECTURE.md)
- [Security policy](../SECURITY.md)
- [Contributing](../CONTRIBUTING.md)
- [PyPI package](https://pypi.org/project/PyVaultRCE/)
