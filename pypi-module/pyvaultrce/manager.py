"""
manager.py — CodeManager implementation for PyVaultRCE
"""

import os
import re
import sys
import traceback
from typing import Optional

try:
    import requests
except ImportError:
    raise ImportError(
        "The 'requests' library is required. Install it with: pip install requests"
    )

_DEFAULT_BASE = os.environ.get("PYVAULT_URL", "http://localhost:5000")
_MAX_LINES    = 10_000
_SID_LEN      = 21
_HEX_SET      = frozenset("0123456789abcdef")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _base(url: Optional[str]) -> str:
    return (url or _DEFAULT_BASE).rstrip("/")


def _valid_sid(sid: str) -> bool:
    return isinstance(sid, str) and len(sid) == _SID_LEN and all(c in _HEX_SET for c in sid)


def _check_sid(sid: str) -> None:
    if not _valid_sid(sid):
        raise ValueError(
            f"Invalid Session ID: '{sid}'. "
            f"Must be exactly {_SID_LEN} lowercase hexadecimal characters."
        )


def _read_file(path: str) -> str:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"File not found: '{path}'. Check the path and try again."
        )
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as fh:
            return fh.read()


def _resolve_paste_url(url: str) -> str:
    """
    Rewrite common paste service URLs to their raw endpoints.
    Supports pastebin.com, hastebin.com, dpaste.com, paste.ofcode.org,
    GitHub Gist raw URLs, and any URL already pointing to raw text.
    """
    # pastebin.com/XXXX → pastebin.com/raw/XXXX
    url = re.sub(
        r"(https?://pastebin\.com/)(?!raw/)([A-Za-z0-9]+)(\?.*)?$",
        r"\1raw/\2",
        url,
    )
    # hastebin.com/XXXX → hastebin.com/raw/XXXX
    url = re.sub(
        r"(https?://hastebin\.com/)(?!raw/)([A-Za-z0-9]+)(\?.*)?$",
        r"\1raw/\2",
        url,
    )
    # dpaste.com/XXXX → dpaste.com/XXXX.txt
    url = re.sub(
        r"(https?://dpaste\.com/)([A-Z0-9]+)(?!\.txt)(\?.*)?$",
        r"\1\2.txt",
        url,
    )
    # paste.ofcode.org/XXXX → paste.ofcode.org/raw/XXXX
    url = re.sub(
        r"(https?://paste\.ofcode\.org/)(?!raw/)([A-Za-z0-9]+)(\?.*)?$",
        r"\1raw/\2",
        url,
    )
    return url


def _http_post(url: str, payload: dict, timeout: int) -> requests.Response:
    try:
        return requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"Unable to connect to PyVault at '{url}'. "
            "Ensure the server is running and PYVAULT_URL is set correctly."
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Request to '{url}' timed out after {timeout}s.")
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"HTTP request failed: {exc}") from exc


def _http_get(url: str, timeout: int, headers: Optional[dict] = None) -> requests.Response:
    try:
        return requests.get(url, timeout=timeout, headers=headers or {})
    except requests.exceptions.ConnectionError:
        _hint = ""
        if "localhost" in url or "127.0.0.1" in url:
            _hint = (
                "\n\n  ✗ PYVAULT_URL is not set — defaulting to localhost will not work "
                "on a phone or remote machine.\n"
                "  → Set it before running:\n"
                "       import os\n"
                "       os.environ['PYVAULT_URL'] = 'https://your-server.replit.app'\n"
                "    or in your shell:\n"
                "       export PYVAULT_URL=https://your-server.replit.app"
            )
        raise ConnectionError(
            f"Unable to connect to PyVault at '{url}'.{_hint}"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Request to '{url}' timed out after {timeout}s.")
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"HTTP request failed: {exc}") from exc


def _upload_code(code: str, base_url: Optional[str], timeout: int) -> str:
    """Internal: push code string to /pyv/save and return the session ID."""
    if not code.strip():
        raise ValueError("Code is empty — nothing to upload.")
    if len(code) > _MAX_CHARS:
        raise ValueError(
            f"Code is {len(code):,} characters, which exceeds the server limit of {_MAX_CHARS:,}."
        )
    url  = _base(base_url) + "/pyv/save"
    resp = _http_post(url, {"code": code}, timeout)
    if resp.status_code != 201:
        try:
            err = resp.json().get("error", resp.text)
        except Exception:
            err = resp.text
        raise RuntimeError(f"Server rejected upload (HTTP {resp.status_code}): {err}")
    data = resp.json()
    sid  = data.get("session_id", "")
    if not _valid_sid(sid):
        raise RuntimeError(f"Server returned unexpected Session ID: '{sid}'")
    return sid


# ── CodeManager ───────────────────────────────────────────────────────────────

class CodeManager:
    """
    Remote code management client for PyVault.

    All methods are static — no instantiation required.

    Typical flow:
        from pyvaultrce import CodeManager

        sid = CodeManager.enc("script.py")
        CodeManager.run(sid)

    Environment variables:
        PYVAULT_URL — base URL of the PyVault server (default: http://localhost:5000)
    """

    @staticmethod
    def enc(
        file_path: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> str:
        """
        Read a local .py file and upload it to PyVault.

        Args:
            file_path: Path to the local Python file.
            base_url:  Override the server URL.
            timeout:   HTTP timeout in seconds.

        Returns:
            The 21-character hex Session ID.

        Raises:
            FileNotFoundError, ValueError, ConnectionError, RuntimeError
        """
        code = _read_file(file_path)
        if not code.strip():
            raise ValueError(f"The file '{file_path}' is empty — nothing to upload.")
        sid = _upload_code(code, base_url, timeout)
        print(f"[PyVault] ✓ Uploaded  — Session ID : {sid}", flush=True)
        print(f"[PyVault]   Source    : {os.path.abspath(file_path)}", flush=True)
        print(f"[PyVault]   Size      : {len(code):,} chars", flush=True)
        return sid

    @staticmethod
    def enc_url(
        paste_url: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> str:
        """
        Download Python code from a paste service URL and upload to PyVault.

        Automatically rewrites paste service links to their raw endpoints
        (pastebin.com, hastebin.com, dpaste.com, paste.ofcode.org, GitHub raw).

        Args:
            paste_url: URL pointing to Python source code.
            base_url:  Override the server URL.
            timeout:   HTTP timeout in seconds.

        Returns:
            The 21-character hex Session ID.

        Raises:
            ValueError, ConnectionError, RuntimeError
        """
        raw_url = _resolve_paste_url(paste_url.strip())
        try:
            resp = requests.get(
                raw_url,
                timeout=timeout,
                headers={"User-Agent": "PyVaultRCE/2.0"},
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Could not fetch code from '{paste_url}'.")
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(
                f"Failed to download from '{paste_url}': HTTP {exc.response.status_code}"
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Timed out fetching '{paste_url}'.")
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"HTTP request failed: {exc}") from exc

        code = resp.text
        if not code.strip():
            raise ValueError("Downloaded content is empty.")

        sid = _upload_code(code, base_url, timeout)
        print(f"[PyVault] ✓ Uploaded from URL — Session ID : {sid}", flush=True)
        print(f"[PyVault]   Source : {paste_url}", flush=True)
        print(f"[PyVault]   Size   : {len(code):,} chars", flush=True)
        return sid

    @staticmethod
    def run(
        session_id: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
        _ns: Optional[dict] = None,
    ) -> None:
        """
        Fetch the code for a Session ID from PyVault and execute it locally.

        The source code is transmitted over the network and run via exec().
        It is never written to disk and is not accessible after execution.

        Args:
            session_id: The 21-character hex Session ID.
            base_url:   Override the server URL.
            timeout:    HTTP timeout in seconds.
            _ns:        Optional namespace dict passed to exec(). Leave as None
                        unless you intentionally want to share a namespace.

        Raises:
            ValueError, ConnectionError, RuntimeError, plus any exception
            raised by the remote code itself.
        """
        _check_sid(session_id)

        url  = _base(base_url) + f"/pyv/get/{session_id}"
        resp = _http_get(url, timeout)

        if resp.status_code == 404:
            try:
                err = resp.json().get("error", "Session not found.")
            except Exception:
                err = "Session not found."
            raise RuntimeError(
                f"Session '{session_id}' not found on the server. {err}"
            )
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RuntimeError(f"Server error (HTTP {resp.status_code}): {err}")

        data      = resp.json()
        code      = data.get("code", "")
        run_count = data.get("execution_count", "?")

        if not code:
            raise RuntimeError(f"Server returned empty code for session '{session_id}'.")

        print(f"[PyVault] ▶ Running session '{session_id}' (execution #{run_count})…", flush=True)

        namespace = _ns if _ns is not None else {
            "__name__": "__pyvault__",
            "__builtins__": __builtins__,
        }

        try:
            exec(compile(code, f"<vault:{session_id[:8]}…>", "exec"), namespace)
        except SyntaxError as exc:
            print(f"\n[PyVault] ✕ Syntax error:", file=sys.stderr, flush=True)
            print(f"  Line {exc.lineno}: {exc.msg}", file=sys.stderr)
            if exc.text:
                print(f"  >>> {exc.text.strip()}", file=sys.stderr)
            raise
        except Exception:
            print(f"\n[PyVault] ✕ Runtime error:", file=sys.stderr, flush=True)
            for line in traceback.format_exc().splitlines():
                print(f"  {line}", file=sys.stderr)
            raise

        print(f"[PyVault] ✓ Execution complete.", flush=True)

    @staticmethod
    def info(
        session_id: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> dict:
        """
        Fetch metadata for a Session ID without executing the code and without
        incrementing the execution counter.

        Returns:
            dict with keys: session_id, execution_count, created_at, code_size

        Raises:
            ValueError, ConnectionError, RuntimeError
        """
        _check_sid(session_id)
        url  = _base(base_url) + f"/pyv/info/{session_id}"
        resp = _http_get(url, timeout)
        if resp.status_code == 404:
            raise RuntimeError(f"Session '{session_id}' not found.")
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RuntimeError(f"Server error (HTTP {resp.status_code}): {err}")
        data = resp.json()
        print(
            f"[PyVault] ℹ Session   : {data['session_id']}\n"
            f"[PyVault]   Executions: {data['execution_count']}\n"
            f"[PyVault]   Created   : {data['created_at']}\n"
            f"[PyVault]   Code size : {data['code_size']:,} chars",
            flush=True,
        )
        return data

    @staticmethod
    def ping(
        base_url: Optional[str] = None,
        timeout: int = 10,
    ) -> bool:
        """
        Check whether the PyVault server is reachable.

        Returns:
            True if server responded with valid stats, False otherwise.
        """
        url = _base(base_url) + "/pyv/stats"
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                d = resp.json()
                print(
                    f"[PyVault] ✓ Server online — "
                    f"{d.get('total_sessions', '?')} sessions, "
                    f"{d.get('total_executions', '?')} total executions.",
                    flush=True,
                )
                return True
        except Exception:
            pass
        print(f"[PyVault] ✕ Server unreachable at '{_base(base_url)}'.", flush=True)
        return False

    @staticmethod
    def edit(
        session_id: str,
        file_path: str,
        admin_token: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """
        Replace the code stored for a Session ID (admin-only operation).

        Requires the admin access token from the PyVault server.

        Args:
            session_id:  The 21-character hex Session ID to update.
            file_path:   Path to the .py file with the new code.
            admin_token: Admin access token (from server console on first start).
            base_url:    Override the server URL.
            timeout:     HTTP timeout in seconds.

        Raises:
            ValueError, FileNotFoundError, ConnectionError, RuntimeError
        """
        _check_sid(session_id)
        if not admin_token or not admin_token.strip():
            raise ValueError("admin_token is required. Check the server console for your token.")

        code = _read_file(file_path)
        if not code.strip():
            raise ValueError(f"The file '{file_path}' is empty — nothing to upload.")
        if len(code) > _MAX_CHARS:
            raise ValueError(f"Code is {len(code):,} chars, exceeds {_MAX_CHARS:,} limit.")

        url = _base(base_url) + f"/pyv/edit/{session_id}"
        try:
            resp = requests.put(
                url,
                json={"code": code},
                headers={"X-Admin-Token": admin_token},
                timeout=timeout,
            )
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Unable to connect to PyVault at '{url}'.")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request timed out after {timeout}s.")
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"HTTP request failed: {exc}") from exc

        if resp.status_code == 403:
            raise RuntimeError("Admin token rejected. Check your token and try again.")
        if resp.status_code == 404:
            raise RuntimeError(f"Session '{session_id}' not found.")
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RuntimeError(f"Server rejected edit (HTTP {resp.status_code}): {err}")

        print(f"[PyVault] ✓ Session '{session_id}' updated.", flush=True)
        print(f"[PyVault]   File : {os.path.abspath(file_path)}", flush=True)
        print(f"[PyVault]   Size : {len(code):,} chars", flush=True)
