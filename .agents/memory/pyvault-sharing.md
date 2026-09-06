---
name: PyVault sharing boundary
description: Product boundary for public share links and library metadata.
---

Short share links are intentionally metadata-only. They may show the session ID, label, status, expiry, execution count, and declared library names, but never render or return source code.

**Why:** Sharing a simple live link is useful, while exposing Python source or owner credentials would undermine the vault boundary.

**How to apply:** Keep share pages separate from source retrieval endpoints and treat all library fields as display metadata.

Declared libraries are informational only. The client must not automatically install arbitrary dependencies on the caller's machine or on the host.

**Why:** Automatic installation expands the trust boundary and can turn a hosted-code workflow into an unreviewed package execution path.

**How to apply:** Users install reviewed dependencies in their own environment; future sandbox work should use an explicit allowlist or reviewed runtime image.