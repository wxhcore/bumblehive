---
name: github
description: Use GitHub CLI workflows for issues, pull requests, CI checks, and repository metadata.
---

# GitHub

Use this skill when a task involves GitHub issues, pull requests, Actions checks, or repository metadata.

Prefer structured `gh` output when possible:

```bash
gh pr view <number> --json title,state,author,headRefName,baseRefName
gh pr checks <number>
gh issue list --json number,title,state
```

If the repository is not obvious from the current working directory, ask for or infer the `owner/repo` value before running commands that need it.
