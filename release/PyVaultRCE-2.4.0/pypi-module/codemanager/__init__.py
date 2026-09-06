"""
codemanager — Remote Code Execution & Hosting PyPI Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Provides the CodeManager class to upload, execute, and edit
Python scripts hosted on a PyVault backend — without exposing
the source code to the client.

Usage:
    from codemanager import CodeManager

    # Upload a local script and get a Session ID
    session_id = CodeManager.enc("my_script.py")

    # Execute the remote script by Session ID
    CodeManager.run(session_id)

    # Push an updated version of the script
    CodeManager.edit(session_id, "my_script_v2.py")
"""

from .manager import CodeManager

__all__ = ["CodeManager"]
__version__ = "2.4.0"
__author__  = "PyVault"
