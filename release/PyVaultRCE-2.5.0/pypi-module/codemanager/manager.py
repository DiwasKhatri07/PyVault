"""
manager.py — CodeManager implementation
"""

import os
import subprocess
import sys
import tempfile
import traceback
import textwrap
from typing import Optional

try:
    import requests
except ImportError:
    raise ImportError(
        "The 'requests' library is required. Install it with: pip install requests"
    )

_DEFAULT_BASE_URL = "https://secure-code-runner--diwasrepl.replit.app"

# ── Validation helpers ───────────────────────────────────────────────────────

def _is_valid_session_id(session_id: str) -> bool:
    return (
        isinstance(session_id, str)
        and len(session_id) == 21
        and all(c in "0123456789abcdef" for c in session_id)
    )


def _validate_session_id(session_id: str) -> None:
    if not _is_valid_session_id(session_id):
        raise ValueError(
            f"Invalid Session ID: '{session_id}'. "
            "A Session ID must be exactly 21 lowercase hexadecimal characters."
        )


def _get_base_url(base_url: Optional[str]) -> str:
    url = (base_url or os.environ.get("PYVAULT_URL") or _DEFAULT_BASE_URL).rstrip("/")
    return url


def _terminal_enabled(show_terminal=None) -> bool:
    if show_terminal is not None:
        return bool(show_terminal)
    return os.environ.get("PYVAULT_TERMINAL", "on").strip().lower() not in {
        "0", "false", "off", "no", "quiet"
    }


def _emit(message: str, show_terminal=None, *, error=False) -> None:
    if _terminal_enabled(show_terminal):
        print(message, file=sys.stderr if error else sys.stdout, flush=True)


def _isolated_run(code: str, session_id: str, timeout: int) -> subprocess.CompletedProcess:
    """Execute in a short-lived process with clean environment and limits."""
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

    clean_env = {
        key: os.environ[key]
        for key in ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "HOME", "LANG", "LC_ALL")
        if key in os.environ
    }
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


# ── CodeManager ─────────────────────────────────────────────────────────────

class CodeManager:
    """
    Remote code management client for PyVault.

    All methods are static so no instantiation is needed:

        from codemanager import CodeManager
        sid = CodeManager.enc("script.py")
        CodeManager.run(sid)
        CodeManager.edit(sid, "script_v2.py")
    """

    @staticmethod
    def enc(
        file_path: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
        label: str = "",
        libraries = "",
        username: str = "",
        description: str = "",
        tags = "",
    ) -> str:
        """
        Read a local Python file and upload it to the PyVault backend.

        Args:
            file_path: Path to the local .py file to upload.
            base_url:  Override the server URL (default: PYVAULT_URL env or hosted PyVault URL).
            timeout:   HTTP timeout in seconds.

        Returns:
            The 21-character hex Session ID assigned to this upload.

        Raises:
            FileNotFoundError: If file_path does not exist.
            ValueError:        If the file is empty.
            ConnectionError:   If the server is unreachable.
            RuntimeError:      If the server returns an error response.
        """
        path = os.path.abspath(file_path)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"File not found: '{file_path}'. "
                "Ensure the path is correct and the file exists."
            )

        try:
            with open(path, "r", encoding="utf-8") as fh:
                code = fh.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as fh:
                code = fh.read()

        if not code.strip():
            raise ValueError(f"The file '{file_path}' is empty. Nothing to upload.")

        url = _get_base_url(base_url) + "/pyv/save"
        try:
            response = requests.post(
                url,
                json={
                    "code": code,
                    "label": label,
                    "libraries": libraries,
                    "username": username,
                    "description": description,
                    "tags": tags,
                },
                timeout=timeout,
            )
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Unable to connect to PyVault at '{url}'. "
                "Ensure the server is running and PYVAULT_URL is set correctly."
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Request to '{url}' timed out after {timeout}s. "
                "Try increasing the timeout parameter or check the server."
            )
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"HTTP request failed: {exc}") from exc

        if response.status_code != 201:
            try:
                err = response.json().get("error", response.text)
            except Exception:
                err = response.text
            raise RuntimeError(
                f"Server rejected the upload (HTTP {response.status_code}): {err}"
            )

        data = response.json()
        session_id = data.get("session_id", "")
        if not _is_valid_session_id(session_id):
            raise RuntimeError(
                f"Server returned an unexpected Session ID format: '{session_id}'"
            )

        print(f"[PyVault] ✓ Code uploaded successfully.")
        print(f"[PyVault]   Session ID : {session_id}")
        print(f"[PyVault]   File       : {path}")
        print(f"[PyVault]   Size       : {len(code)} characters")
        return session_id

    @staticmethod
    def run(
        session_id: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
        globals_dict: Optional[dict] = None,
        show_terminal=None,
        isolated: bool = True,
    ) -> None:
        """
        Fetch the code for a Session ID from PyVault and execute it in a
        short-lived isolated subprocess by default.

        The source code is fetched over the network. The default subprocess
        uses a clean environment, a temporary working directory, and resource
        limits. Use isolated=False only for trusted code that needs a shared
        in-process namespace.

        Args:
            session_id:   The 21-character hex Session ID.
            base_url:     Override the server URL.
            timeout:      HTTP timeout in seconds.
            globals_dict: Optional globals dict passed to exec(). If None,
                          a clean namespace is used to avoid polluting the
                          caller's namespace.

        Raises:
            ValueError:    If the Session ID format is invalid.
            ConnectionError: If the server is unreachable.
            RuntimeError:  If the session is not found or the server errors.
            Exception:     Re-raises any exception that occurs during exec().
        """
        _validate_session_id(session_id)

        url = _get_base_url(base_url) + f"/pyv/get/{session_id}"
        try:
            response = requests.get(url, timeout=timeout)
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Unable to connect to PyVault at '{url}'. "
                "Ensure the server is running and PYVAULT_URL is set correctly."
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Request timed out after {timeout}s while fetching session '{session_id}'."
            )
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"HTTP request failed: {exc}") from exc

        if response.status_code == 404:
            try:
                err = response.json().get("error", "Session not found.")
            except Exception:
                err = "Session not found."
            raise RuntimeError(
                f"Session ID '{session_id}' was not found on the server. "
                f"Server message: {err}"
            )

        if response.status_code != 200:
            try:
                err = response.json().get("error", response.text)
            except Exception:
                err = response.text
            raise RuntimeError(
                f"Server error (HTTP {response.status_code}): {err}"
            )

        data = response.json()
        code = data.get("code", "")
        exec_count = data.get("execution_count", "?")

        if not code:
            raise RuntimeError(
                f"Server returned empty code for session '{session_id}'."
            )

        _emit(
            f"[PyVault] Executing session '{session_id}' "
            f"(run #{exec_count}, isolated={isolated})…",
            show_terminal,
        )

        if isolated:
            if globals_dict is not None:
                raise ValueError("isolated=True cannot use globals_dict; pass isolated=False for a shared namespace.")
            result = _isolated_run(code, session_id, timeout)
            _emit_child_output(result)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Isolated session '{session_id}' exited with code {result.returncode}."
                )
        else:
            namespace = globals_dict if globals_dict is not None else {
                "__name__": "__pyvault__",
                "__builtins__": __builtins__,
            }
            try:
                compiled = compile(code, f"<pyvault:{session_id}>", "exec")
                exec(compiled, namespace)
            except SyntaxError as exc:
                _emit("\n[PyVault] ✕ Syntax error in remote code:", show_terminal, error=True)
                _emit(f"  Line {exc.lineno}: {exc.msg}", show_terminal, error=True)
                if exc.text:
                    _emit(f"  >>> {exc.text.strip()}", show_terminal, error=True)
                raise
            except Exception:
                _emit("\n[PyVault] ✕ Runtime error during execution:", show_terminal, error=True)
                tb_lines = traceback.format_exc().splitlines()
                for line in tb_lines:
                    _emit(f"  {line}", show_terminal, error=True)
                raise

        _emit("[PyVault] ✓ Execution complete.", show_terminal)

    @staticmethod
    def edit(
        session_id: str,
        file_path: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        """
        Read a local Python file and push it as an update to an existing session.

        Args:
            session_id: The 21-character hex Session ID to update.
            file_path:  Path to the local .py file with the updated code.
            base_url:   Override the server URL.
            timeout:    HTTP timeout in seconds.

        Raises:
            ValueError:       If the Session ID format is invalid.
            FileNotFoundError: If file_path does not exist.
            ValueError:       If the file is empty.
            ConnectionError:  If the server is unreachable.
            RuntimeError:     If the session is not found or the server errors.
        """
        _validate_session_id(session_id)

        path = os.path.abspath(file_path)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"File not found: '{file_path}'. "
                "Ensure the path is correct and the file exists."
            )

        try:
            with open(path, "r", encoding="utf-8") as fh:
                code = fh.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as fh:
                code = fh.read()

        if not code.strip():
            raise ValueError(f"The file '{file_path}' is empty. Nothing to upload.")

        url = _get_base_url(base_url) + f"/pyv/edit/{session_id}"
        try:
            response = requests.put(
                url,
                json={"code": code},
                timeout=timeout,
            )
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Unable to connect to PyVault at '{url}'. "
                "Ensure the server is running and PYVAULT_URL is set correctly."
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Request timed out after {timeout}s while editing session '{session_id}'."
            )
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"HTTP request failed: {exc}") from exc

        if response.status_code == 404:
            try:
                err = response.json().get("error", "Session not found.")
            except Exception:
                err = "Session not found."
            raise RuntimeError(
                f"Session ID '{session_id}' was not found. Cannot edit a non-existent session. "
                f"Server message: {err}"
            )

        if response.status_code != 200:
            try:
                err = response.json().get("error", response.text)
            except Exception:
                err = response.text
            raise RuntimeError(
                f"Server rejected the edit (HTTP {response.status_code}): {err}"
            )

        print(f"[PyVault] ✓ Session '{session_id}' updated successfully.")
        print(f"[PyVault]   File : {path}")
        print(f"[PyVault]   Size : {len(code)} characters")
