---
name: PyVault client isolation
description: Client-side subprocess isolation is defense-in-depth and must preserve Python startup compatibility.
---

The PyVault clients run fetched code in a short-lived subprocess by default, with a clean environment, temporary working directory, timeout, CPU/file limits, and an address-space ceiling. This is not a complete VM or container sandbox.

**Why:** A 512 MiB virtual-memory limit prevented Python from starting on the Linux runtime because the interpreter reserves address space during startup; the practical ceiling must leave room for interpreter startup.

**How to apply:** Keep the default isolated mode for untrusted sessions, document `isolated=False` as an explicit trusted-code escape hatch, and use a dedicated VM/container worker when hostile-code isolation is required.