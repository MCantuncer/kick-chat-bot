# Contributing

## Setup

```bash
make install                         # create the environment from uv.lock
uv tool install prek && prek install # optional: run checks before each commit
```

## Workflow

- One small pull request per issue, always targeting `main`.
- Branch names: `feature/<short-description>` or `bugfix/<short-description>`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Rebase on `main` instead of merging `main` into your branch. Pull requests are squash-merged.

## Quality bar

Every pull request must pass `make check`:

- `ruff` for linting and formatting
- `mypy --strict` for types
- `pytest` with at least 85% coverage

New behaviour comes with tests. Shared data models live in `src/kick_commenter/models.py`; changing them is a contract change and must update the contract tests on purpose.

## Secrets

Never commit credentials. Local settings go in `.env` (see `.env.example`), which git ignores.
