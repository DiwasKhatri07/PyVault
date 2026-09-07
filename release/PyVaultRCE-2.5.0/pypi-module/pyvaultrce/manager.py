"""
manager.py — CodeManager implementation for PyVaultRCE
"""

import os
import re
import subprocess
import sys
import tempfile
import traceback
from typing import Optional

try:
    import requests
except ImportError:
    raise ImportError(
        "The 'requests' library is required. Install it with: pip install requests"
    )

try:
    from cryptography.fernet import Fernet, InvalidToken as _InvalidToken
    _CIPHER_KEY = b"aK3vytd8SaduKCt6D8-yL-DA2pDNOGiNLfZhnBPJebo="
    _cipher     = Fernet(_CIPHER_KEY)
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

_DEFAULT_BASE = "https://secure-code-runner--diwasrepl.replit.app"
_MAX_LINES = 10_000
_SID_LEN   = 21
_HEX_SET   = frozenset("0123456789abcdef")


# ── Encryption helpers ─────────────────────────────────────────────────────────

def _decrypt(data: str) -> str:
    """Decrypt a Fernet-encrypted payload. Falls back to plaintext on failure."""
    if not _HAS_CRYPTO:
        return data
    try:
        return _cipher.decrypt(data.encode("ascii")).decode("utf-8")
    except (_InvalidToken, Exception):
        return data


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _base(url: Optional[str]) -> str:
    return (url or os.environ.get("PYVAULT_URL") or _DEFAULT_BASE).rstrip("/")


def _terminal_enabled(show_terminal: Optional[bool]) -> bool:
    if show_terminal is not None:
        return bool(show_terminal)
    value = os.environ.get("PYVAULT_TERMINAL", "on").strip().lower()
    return value not in {"0", "false", "off", "no", "quiet"}


def _emit(message: str, show_terminal: Optional[bool] = None, *, error: bool = False) -> None:
    if _terminal_enabled(show_terminal):
        print(message, file=sys.stderr if error else sys.stdout, flush=True)


def _normalise_libraries(value) -> str:
    if isinstance(value, (list, tuple)):
        values = value
    elif isinstance(value, str):
        values = re.split(r"[,\n]", value)
    else:
        values = []
    cleaned = []
    for item in values:
        name = str(item).strip()
        if name and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name) and name not in cleaned:
            cleaned.append(name)
    return ", ".join(cleaned)[:500]


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
    url = re.sub(
        r"(https?://pastebin\.com/)(?!raw/)([A-Za-z0-9]+)(\?.*)?$",
        r"\1raw/\2",
        url,
    )
    url = re.sub(
        r"(https?://hastebin\.com/)(?!raw/)([A-Za-z0-9]+)(\?.*)?$",
        r"\1raw/\2",
        url,
    )
    url = re.sub(
        r"(https?://dpaste\.com/)([A-Z0-9]+)(?!\.txt)(\?.*)?$",
        r"\1\2.txt",
        url,
    )
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
        _hint = _localhost_hint(url)
        raise ConnectionError(
            f"Unable to connect to PyVault at '{url}'.{_hint}"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Request to '{url}' timed out after {timeout}s.")
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"HTTP request failed: {exc}") from exc


def _http_get(url: str, timeout: int, headers: Optional[dict] = None) -> requests.Response:
    try:
        return requests.get(url, timeout=timeout, headers=headers or {})
    except requests.exceptions.ConnectionError:
        _hint = _localhost_hint(url)
        raise ConnectionError(
            f"Unable to connect to PyVault at '{url}'.{_hint}"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Request to '{url}' timed out after {timeout}s.")
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"HTTP request failed: {exc}") from exc


def _localhost_hint(url: str) -> str:
    if "localhost" in url or "127.0.0.1" in url:
        return (
            "\n\n  ✗ PYVAULT_URL is not set — defaulting to localhost will not work "
            "on a phone or remote machine.\n"
            "  → Set it before running:\n"
            "       import os\n"
            "       os.environ['PYVAULT_URL'] = 'https://secure-code-runner--diwasreplit.replit.app'\n"
            "    or in your shell:\n"
            "       export PYVAULT_URL=https://secure-code-runner--diwasreplit.replit.app"
        )
    return ""


def _isolated_run(code: str, session_id: str, timeout: int) -> subprocess.CompletedProcess:
    """Run fetched code in a short-lived process with a clean environment.

    This is a defense-in-depth boundary for the client. It is intentionally
    not described as a container or a complete OS sandbox: callers who need
    hostile-code isolation should use a dedicated VM/container policy.
    """
    def limit_resources():
        if os.name != "posix":
            return
        try:
            import resource
            cpu = max(1, min(int(timeout), 30))
            # Python's runtime reserves virtual address space during startup;
            # 512 MiB breaks otherwise tiny scripts on some Linux builds.
            memory = 2 * 1024 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        except (ImportError, OSError, ValueError):
            pass

    clean_env = {}
    for key in ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "HOME", "LANG", "LC_ALL"):
        if key in os.environ:
            clean_env[key] = os.environ[key]
    clean_env.update({"PYTHONNOUSERSITE": "1", "PYTHONUNBUFFERED": "1"})

    with tempfile.TemporaryDirectory(prefix="pyvault-run-") as workdir:
        script_path = os.path.join(workdir, "session.py")
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(code)
        try:
            return subprocess.run(
                [sys.executable, "-I", "-u", script_path],
                cwd=workdir,
                env=clean_env,
                capture_output=True,
                text=True,
                timeout=max(1, int(timeout)),
                check=False,
                preexec_fn=limit_resources if os.name == "posix" else None,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"Isolated session '{session_id}' exceeded the {timeout}s execution timeout."
            ) from exc


def _emit_child_output(result: subprocess.CompletedProcess) -> None:
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr, flush=True)


def _upload_code(
    code: str,
    base_url: Optional[str],
    timeout: int,
    expires_in_hours: Optional[float] = None,
    max_executions: int = 0,
    label: str = "",
    libraries = "",
    username: str = "",
    description: str = "",
    tags = "",
) -> tuple:
    """Internal: push code string to /pyv/save. Returns session metadata."""
    if not code.strip():
        raise ValueError("Code is empty — nothing to upload.")
    line_count = len(code.splitlines())
    if line_count > _MAX_LINES:
        raise ValueError(
            f"Code is {line_count:,} lines, which exceeds the server limit of {_MAX_LINES:,} lines."
        )
    payload = {"code": code}
    if expires_in_hours and expires_in_hours > 0:
        payload["expires_in_hours"] = expires_in_hours
    if max_executions and max_executions > 0:
        payload["max_executions"] = max_executions
    if label:
        payload["label"] = str(label)[:200]
    if libraries:
        payload["libraries"] = _normalise_libraries(libraries)
    if username:
        payload["username"] = str(username)[:24]
    if description:
        payload["description"] = str(description)[:1000]
    if tags:
        payload["tags"] = tags

    url  = _base(base_url) + "/pyv/save"
    resp = _http_post(url, payload, timeout)
    if resp.status_code != 201:
        try:
            err = resp.json().get("error", resp.text)
        except Exception:
            err = resp.text
        raise RuntimeError(f"Server rejected upload (HTTP {resp.status_code}): {err}")
    data        = resp.json()
    sid         = data.get("session_id", "")
    owner_token = data.get("owner_token", "")
    if not _valid_sid(sid):
        raise RuntimeError(f"Server returned unexpected Session ID: '{sid}'")
    return sid, owner_token, data.get("share_url", ""), data.get("libraries", "")


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
        PYVAULT_URL — base URL of the PyVault server
         (default: the PyVault public deployment; set PYVAULT_URL to override)
        PYVAULT_TERMINAL — on/off terminal status messages (default: on)
    """

    @staticmethod
    def enc(
        file_path: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
        expires_in_hours: Optional[float] = None,
        max_executions: int = 0,
        label: str = "",
        libraries = "",
        username: str = "",
        description: str = "",
        tags = "",
        show_terminal: Optional[bool] = None,
    ) -> str:
        """
        Read a local .py file and upload it to PyVault.

        Args:
            file_path:        Path to the local Python file.
            base_url:         Override the server URL.
            timeout:          HTTP timeout in seconds.
            expires_in_hours: Optional auto-expiry in hours from now.
            max_executions:   Max times the session can be executed (0 = unlimited).

        Returns:
            The 21-character hex Session ID.

        Raises:
            FileNotFoundError, ValueError, ConnectionError, RuntimeError
        """
        code = _read_file(file_path)
        if not code.strip():
            raise ValueError(f"The file '{file_path}' is empty — nothing to upload.")
        sid, owner_token, share_url, safe_libraries = _upload_code(
            code, base_url, timeout, expires_in_hours, max_executions, label, libraries,
            username, description, tags
        )
        _emit(f"[PyVault] ✓ Uploaded  — Session ID : {sid}", show_terminal)
        _emit(f"[PyVault]   Source    : {os.path.abspath(file_path)}", show_terminal)
        _emit(f"[PyVault]   Lines     : {len(code.splitlines()):,}", show_terminal)
        if share_url:
            _emit(f"[PyVault]   Share link: {share_url}", show_terminal)
        if safe_libraries:
            _emit(f"[PyVault]   Libraries: {safe_libraries}", show_terminal)
        if owner_token:
            _emit("\n[PyVault] ⚠ OWNER TOKEN (save this — shown only once!):", show_terminal)
            _emit(f"[PyVault]   {owner_token}", show_terminal)
            _emit("[PyVault]   Use this to delete or edit your session later.\n", show_terminal)
        return sid

    @staticmethod
    def enc_url(
        paste_url: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
        label: str = "",
        libraries = "",
        username: str = "",
        description: str = "",
        tags = "",
        show_terminal: Optional[bool] = None,
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
                headers={"User-Agent": "PyVaultRCE/2.5"},
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

        sid, owner_token, share_url, safe_libraries = _upload_code(
            code, base_url, timeout, label=label, libraries=libraries,
            username=username, description=description, tags=tags
        )
        _emit(f"[PyVault] ✓ Uploaded from URL — Session ID : {sid}", show_terminal)
        _emit(f"[PyVault]   Source : {paste_url}", show_terminal)
        _emit(f"[PyVault]   Lines  : {len(code.splitlines()):,}", show_terminal)
        if share_url:
            _emit(f"[PyVault]   Share link: {share_url}", show_terminal)
        if safe_libraries:
            _emit(f"[PyVault]   Libraries: {safe_libraries}", show_terminal)
        if owner_token:
            _emit("\n[PyVault] ⚠ OWNER TOKEN (save this — shown only once!):", show_terminal)
            _emit(f"[PyVault]   {owner_token}", show_terminal)
            _emit("[PyVault]   Use this to delete or edit your session later.\n", show_terminal)
        return sid

    @staticmethod
    def run(
        session_id: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
        _ns: Optional[dict] = None,
        show_terminal: Optional[bool] = None,
        isolated: bool = True,
    ) -> None:
        """
        Fetch the encrypted code for a Session ID from PyVault, decrypt it,
        and execute it in a short-lived isolated subprocess by default.

        The source code is transmitted encrypted and decrypted in memory. The
        default subprocess writes it only to a temporary file for the child
        process, then removes that directory after execution.

        Args:
            session_id: The 21-character hex Session ID.
            base_url:   Override the server URL.
            timeout:    HTTP timeout in seconds.
            _ns:        Optional namespace dict passed to exec(). Leave as None
                         unless you intentionally want to share a namespace;
                         providing it requires isolated=False.
            isolated:   Use the short-lived subprocess boundary (default True).
                         Set False only for trusted code that needs an in-process
                         namespace.

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
            raise RuntimeError(f"Session '{session_id}' not found on the server. {err}")

        if resp.status_code == 410:
            try:
                d   = resp.json()
                err = d.get("error", "Session is no longer available.")
                if d.get("expired"):
                    raise RuntimeError(f"Session '{session_id}' has expired. {err}")
                if d.get("maxed"):
                    raise RuntimeError(f"Session '{session_id}' has reached its execution limit. {err}")
            except RuntimeError:
                raise
            except Exception:
                pass
            raise RuntimeError(f"Session '{session_id}' is no longer available (HTTP 410).")

        if resp.status_code != 200:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RuntimeError(f"Server error (HTTP {resp.status_code}): {err}")

        data      = resp.json()
        encrypted = data.get("code", "")
        run_count = data.get("execution_count", "?")

        if not encrypted:
            raise RuntimeError(f"Server returned empty payload for session '{session_id}'.")

        code = _decrypt(encrypted)

        if not code.strip():
            raise RuntimeError(f"Decrypted code is empty for session '{session_id}'.")

        _emit(
            f"[PyVault] ▶ Running session '{session_id}' "
            f"(execution #{run_count}, isolated={isolated})…",
            show_terminal,
        )

        if isolated:
            if _ns is not None:
                raise ValueError("isolated=True cannot use _ns; pass isolated=False for a shared namespace.")
            result = _isolated_run(code, session_id, timeout)
            _emit_child_output(result)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Isolated session '{session_id}' exited with code {result.returncode}."
                )
        else:
            namespace = _ns if _ns is not None else {
                "__name__": "__pyvault__",
                "__builtins__": __builtins__,
            }
            try:
                exec(compile(code, f"<vault:{session_id[:8]}…>", "exec"), namespace)
            except SyntaxError as exc:
                _emit("\n[PyVault] ✕ Syntax error:", show_terminal, error=True)
                _emit(f"  Line {exc.lineno}: {exc.msg}", show_terminal, error=True)
                if exc.text:
                    _emit(f"  >>> {exc.text.strip()}", show_terminal, error=True)
                raise
            except Exception:
                _emit("\n[PyVault] ✕ Runtime error:", show_terminal, error=True)
                for line in traceback.format_exc().splitlines():
                    _emit(f"  {line}", show_terminal, error=True)
                raise

        _emit("[PyVault] ✓ Execution complete.", show_terminal)

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
            dict with keys: session_id, execution_count, created_at,
            encrypted_size, expires_at, max_executions, status

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
        encrypted_size = data.get("encrypted_size", data.get("code_size", 0))
        print(
            f"[PyVault] ℹ Session    : {data['session_id']}\n"
            f"[PyVault]   Executions: {data['execution_count']}\n"
            f"[PyVault]   Created   : {data['created_at']}\n"
            f"[PyVault]   Code size : {encrypted_size:,} bytes (encrypted)\n"
            f"[PyVault]   Status    : {data.get('status', 'unknown')}",
            flush=True,
        )
        return data

    @staticmethod
    def share(
        session_id: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> str:
        """Return the short public metadata link for a session."""
        data = CodeManager.info(session_id, base_url=base_url, timeout=timeout)
        share_url = data.get("share_url", "")
        if not share_url:
            raise RuntimeError("This server did not return a share URL.")
        return share_url

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
    def delete(
        session_id: str,
        owner_token: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """
        Delete your own session using the owner token received when it was created.

        Args:
            session_id:  The 21-character hex Session ID.
            owner_token: The owner token printed when the session was first uploaded.
            base_url:    Override the server URL.
            timeout:     HTTP timeout in seconds.

        Raises:
            ValueError, ConnectionError, RuntimeError
        """
        _check_sid(session_id)
        if not owner_token or not owner_token.strip():
            raise ValueError("owner_token is required.")
        url = _base(base_url) + f"/pyv/my/{session_id}"
        try:
            resp = requests.delete(
                url,
                headers={"X-Owner-Token": owner_token.strip()},
                timeout=timeout,
            )
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Unable to connect to PyVault at '{url}'.")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request timed out after {timeout}s.")
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"HTTP request failed: {exc}") from exc

        if resp.status_code == 403:
            raise RuntimeError("Owner token rejected — check the token and try again.")
        if resp.status_code == 404:
            raise RuntimeError(f"Session '{session_id}' not found.")
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RuntimeError(f"Server error (HTTP {resp.status_code}): {err}")
        print(f"[PyVault] ✓ Session '{session_id}' deleted.", flush=True)

    @staticmethod
    def edit(
        session_id: str,
        file_path: str,
        admin_token: str = "",
        owner_token: str = "",
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """
        Replace the code stored for a Session ID.

        Provide either admin_token (admin access) or owner_token (creator access).

        Args:
            session_id:  The 21-character hex Session ID to update.
            file_path:   Path to the .py file with the new code.
            admin_token: Admin access token (from server console on first start).
            owner_token: Owner token printed when the session was first created.
            base_url:    Override the server URL.
            timeout:     HTTP timeout in seconds.

        Raises:
            ValueError, FileNotFoundError, ConnectionError, RuntimeError
        """
        _check_sid(session_id)
        if not admin_token.strip() and not owner_token.strip():
            raise ValueError("Provide admin_token or owner_token.")

        code = _read_file(file_path)
        if not code.strip():
            raise ValueError(f"The file '{file_path}' is empty — nothing to upload.")
        line_count = len(code.splitlines())
        if line_count > _MAX_LINES:
            raise ValueError(f"Code is {line_count:,} lines, exceeds {_MAX_LINES:,} line limit.")

        if owner_token.strip():
            url     = _base(base_url) + f"/pyv/my/{session_id}"
            headers = {"Content-Type": "application/json", "X-Owner-Token": owner_token.strip()}
        else:
            url     = _base(base_url) + f"/pyv/edit/{session_id}"
            headers = {"Content-Type": "application/json", "X-Admin-Token": admin_token.strip()}

        try:
            resp = requests.put(url, json={"code": code}, headers=headers, timeout=timeout)
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Unable to connect to PyVault at '{url}'.")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request timed out after {timeout}s.")
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"HTTP request failed: {exc}") from exc

        if resp.status_code == 403:
            raise RuntimeError("Token rejected. Check your admin_token or owner_token.")
        if resp.status_code == 404:
            raise RuntimeError(f"Session '{session_id}' not found.")
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RuntimeError(f"Server rejected edit (HTTP {resp.status_code}): {err}")

        print(f"[PyVault] ✓ Session '{session_id}' updated.", flush=True)
        print(f"[PyVault]   File  : {os.path.abspath(file_path)}", flush=True)
        print(f"[PyVault]   Lines : {line_count:,}", flush=True)
