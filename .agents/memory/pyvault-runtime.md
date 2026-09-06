---
name: PyVault runtime reliability
description: Durable runtime and migration lessons for the Flask session host.
---

PyVault must initialize its SQLite schema during application import as well as direct development startup, because WSGI production servers import the Flask app without entering the main module branch.

**Why:** The production server imported the app successfully but skipped the old startup-only initialization path, which surfaced later as route-level failures.

**How to apply:** Keep initialization idempotent and concurrency-safe, and use busy timeouts/WAL for SQLite access.

Legacy SQLite migrations can leave numeric-looking values with text affinity. Normalize values at query or response boundaries before templates compare them numerically.

**Why:** Existing session rows caused a dashboard render failure even though the stored values represented valid limits.

**How to apply:** Cast numeric fields in admin queries and coerce detail-page data before rendering.