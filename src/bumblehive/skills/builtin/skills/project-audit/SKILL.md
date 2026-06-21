---
name: project-audit
description: Inspect a Python project structure, run focused tests, and summarize implementation risks.
---

# Project Audit

Use this skill when the user asks to inspect, review, or sanity-check a local Python project.

Start by identifying the project layout:

```bash
rg --files
```

Then inspect the narrow files related to the request. Prefer focused tests first, then broaden to the full suite when the change touches shared behavior.

When reporting back, lead with concrete findings and include the exact commands that were run.
