# PyVaultRCE

Remote Code Execution & Hosting client for **PyVault**.

Upload Python scripts to a PyVault server and execute them remotely — the source code **never leaves the server**. Clients only ever hold a 21-character hex Session ID.

## Install

```bash
pip install PyVaultRCE
```

## Quick Start

```python
from pyvaultrce import CodeManager

# Upload a local .py file → get a 21-character Session ID
sid = CodeManager.enc("my_script.py")
# [PyVault] ✓ Uploaded  — Session ID : 3a7f1c9b2d0e8a5f41c7e

# Upload from a paste service URL
sid = CodeManager.enc_url("https://pastebin.com/abcXYZ123")

# Execute remotely (source stays on server)
CodeManager.run(sid)

# Check metadata without incrementing execution counter
CodeManager.info(sid)

# Verify server is up
CodeManager.ping()
```

## Configuration

Set `PYVAULT_URL` to point at your hosted PyVault server:

```bash
export PYVAULT_URL=https://your-server.replit.app
```

## API Reference

| Method | Description |
|--------|-------------|
| `CodeManager.enc(file_path)` | Upload a local `.py` file → returns Session ID |
| `CodeManager.enc_url(url)` | Download code from a paste URL and upload → returns Session ID |
| `CodeManager.run(session_id)` | Fetch and execute code by Session ID |
| `CodeManager.info(session_id)` | Get session metadata (no exec count increment) |
| `CodeManager.ping()` | Check server connectivity |
| `CodeManager.edit(session_id, file_path, admin_token=...)` | Replace stored code (admin or owner token) |
| `CodeManager.delete(session_id, owner_token)` | Delete your own session |

## Supported Paste Services (`enc_url`)

- `pastebin.com`
- `hastebin.com`
- `dpaste.com`
- `paste.ofcode.org`
- GitHub raw URLs
- Any URL returning raw Python text

## Error Handling

| Exception | When |
|---|---|
| `FileNotFoundError` | Local file not found |
| `ValueError` | Invalid Session ID or empty file |
| `ConnectionError` | Server unreachable |
| `TimeoutError` | Request timed out |
| `RuntimeError` | Server error (404, 403, 500, etc.) |
| `SyntaxError` | Remote code syntax error (during `run`) |

## Security

- Session IDs are 21-character cryptographically random hex strings
- Source code is never written to disk on the client
- Code is encrypted at rest with Fernet on the server
- Admin edits require the admin access code; owner edits/deletes require the one-time owner token
- Sessions never expire unless an expiry is explicitly selected

## License

MIT
