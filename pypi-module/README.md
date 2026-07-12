# codemanager

Remote Code Execution & Hosting client for **PyVault**.

Upload Python scripts, get a 21-digit hex Session ID, and execute them
remotely — the source code is never exposed to the client.

## Install

```bash
pip install codemanager
```

Or install locally from this directory:

```bash
pip install .
```

## Quick Start

```python
from codemanager import CodeManager

# 1. Upload a local script — get a Session ID back
session_id = CodeManager.enc("my_script.py")
# [PyVault] ✓ Code uploaded.  Session ID: a3f9b1c4d2e8f70a21b

# 2. Execute the remote script anywhere (source not exposed)
CodeManager.run(session_id)

# 3. Push an updated version later
CodeManager.edit(session_id, "my_script_v2.py")
```

## Configuration

Set the `PYVAULT_URL` environment variable to point at your server:

```bash
export PYVAULT_URL=https://your-pyvault-server.com
```

Or pass `base_url` per call:

```python
CodeManager.enc("script.py", base_url="https://your-server.com")
CodeManager.run(session_id, base_url="https://your-server.com")
```

## API Reference

### `CodeManager.enc(file_path, base_url=None, timeout=30) → str`

Upload a local `.py` file to PyVault. Returns the 21-character hex Session ID.

### `CodeManager.run(session_id, base_url=None, timeout=30, globals_dict=None) → None`

Fetch the code for `session_id` and execute it via `exec()`. The
`execution_count` on the server is incremented automatically.

### `CodeManager.edit(session_id, file_path, base_url=None, timeout=30) → None`

Replace the stored code for `session_id` with the contents of `file_path`.

## Error Handling

All methods raise descriptive exceptions:

| Exception | When |
|---|---|
| `FileNotFoundError` | Local file path not found |
| `ValueError` | Invalid Session ID format or empty file |
| `ConnectionError` | Server unreachable |
| `TimeoutError` | HTTP request timed out |
| `RuntimeError` | Server returned error (404, 500, etc.) |
| `SyntaxError` | Remote code has a syntax error (during `run`) |

```python
try:
    CodeManager.run("invalid_or_expired_id")
except ValueError as e:
    print(f"Bad session ID: {e}")
except RuntimeError as e:
    print(f"Server error: {e}")
except Exception as e:
    print(f"Execution error: {e}")
```
