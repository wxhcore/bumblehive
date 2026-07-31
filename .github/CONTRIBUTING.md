# Contributing to BumbleHive

Thank you for helping improve BumbleHive. Contributions to the Python SDK,
Server, WebUI, Desktop application, examples, and documentation are welcome.

## Before You Start

- Search existing issues before opening a new one.
- Use a private
  [GitHub Security Advisory](https://github.com/wxhcore/bumblehive/security/advisories/new)
  for security vulnerabilities.
- Keep each change focused on one problem.
- Never commit API keys, tokens, session data, or personal information.

## Set Up the Project

BumbleHive requires Python 3.11+, Node.js 22.12+, and pnpm 10.33.0.

Fork the repository, then clone your fork:

```bash
git clone https://github.com/<your-username>/bumblehive.git
cd bumblehive
git remote add upstream https://github.com/wxhcore/bumblehive.git
conda create -n bumblehive_env python=3.11 -y
conda activate bumblehive_env
pnpm run setup
```

Start the Server and WebUI:

```bash
pnpm run dev
```

## Make a Change

1. Create a branch from `main`.
2. Follow the existing code style and keep the implementation small.
3. Add or update tests when behavior changes.
4. Update documentation when public behavior or configuration changes.
5. Run the checks relevant to your change.

Common checks:

```bash
# Python SDK
pnpm test

# Server
python -m pytest server/tests

# WebUI
pnpm --filter bumblehive-webui run test
pnpm --filter bumblehive-webui run build

# Desktop, when the platform toolchain is installed
pnpm run build:desktop
```

## Open a Pull Request

Describe:

- the problem being solved;
- the main changes;
- the checks you ran;
- any behavior, configuration, or compatibility impact.

Link related issues when applicable. Maintainers may ask for smaller changes,
additional tests, or documentation before merging.

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](../LICENSE).
