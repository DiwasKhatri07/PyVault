# Contributing to PyVault

Thank you for helping improve PyVault. Contributions should be focused, reproducible, and compatible with the project's security model.

## Development setup

```bash
git clone https://github.com/DiwasKhatri07/PyVault.git
cd PyVault
python -m venv .venv
. .venv/bin/activate
python -m pip install -r artifacts/rce-platform/requirements.txt
```

Run the server with `cd artifacts/rce-platform && python app.py`. For client work, install the package locally with `python -m pip install -e pypi-module`.

## Pull requests

1. Open an issue for substantial features or behavior changes.
2. Keep commits small and describe the user impact.
3. Update documentation and examples when the API changes.
4. Add or update tests and include the exact commands used to verify them.
5. Never commit tokens, session IDs, databases, generated build output, or user code.

Please do not describe PyVault as a complete hostile-code sandbox. Security-sensitive changes require an explicit threat model in the pull request.

## Commit style

Use concise imperative subjects, such as `Improve session validation` or `Document local deployment`.

## Review expectations

Pull requests are reviewed for correctness, backwards compatibility, privacy, and operational safety. Maintainers may request changes or decline features that weaken authorization boundaries.
