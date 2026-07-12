"""
pyvaultrce — Remote Code Execution & Hosting Module for PyVault
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upload Python scripts to a PyVault server and execute them remotely.
The source code never leaves the server — clients only ever hold a
21-character hex Session ID.

Quick start:
    from pyvaultrce import CodeManager

    sid = CodeManager.enc("script.py")          # upload local file
    sid = CodeManager.enc_url("https://...")     # upload from paste URL
    CodeManager.run(sid)                         # execute remotely
    CodeManager.info(sid)                        # check metadata
    CodeManager.ping()                           # verify server is up
"""

from .manager import CodeManager

__all__    = ["CodeManager"]
__version__ = "2.0.0"
__author__  = "PyVault"
