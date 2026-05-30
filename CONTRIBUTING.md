# Contributing to ComfyUI-Pack-Of-ThatAIGod

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/thataigod/ComfyUI-Pack-Of-ThatAIGod.git
cd ComfyUI-Pack-Of-ThatAIGod
pip install -e ".[dev]"
```

## Pre-commit Hooks

Install pre-commit hooks to automatically lint and format on commit:

```bash
pre-commit install
```

This runs:
- **ruff** -- lint and auto-fix
- **ruff-format** -- code formatting
- **mypy** -- type checking
- **trailing-whitespace** / **end-of-file-fixer** -- whitespace cleanup

## Running Tests

```bash
pytest                    # run all tests
pytest -v                 # verbose output
pytest --cov              # with coverage report
pytest tests/test_utils.py  # run specific test file
```

All tests must pass with 100% source code coverage before submitting a PR.

## Code Style

- Python 3.10+ required (uses `X | None` union syntax)
- Type annotations on all function signatures
- Named constants for magic numbers
- No inline comments unless logic is non-obvious
- Follow existing patterns in the codebase

## Adding a New Node

1. Create `YourNode.py` following the existing node pattern:
   - Class with `DESCRIPTION`, `RETURN_TYPES`, `RETURN_NAMES`, `FUNCTION`, `CATEGORY`
   - `INPUT_TYPES()` classmethod
   - Implementation method
   - `NODE_CLASS_MAPPINGS` and `NODE_DISPLAY_NAME_MAPPINGS` at module level
2. Add the module name to `_modules` list in `__init__.py`
3. Create `tests/test_your_node.py` with comprehensive tests
4. Add docstrings to all public methods

## Adding Wildcards

1. Create a `.txt` file in `wildcards/` or `wildcards/autowildcards/`
2. One entry per line; use `#` for comments
3. Reference in prompts as `__filename__` (without `.txt`)

## Pull Request Process

1. Create a feature branch from `master`
2. Make your changes with tests
3. Ensure `pytest` passes with 100% source coverage
4. Ensure `ruff check .` passes
5. Ensure `mypy *.py --ignore-missing-imports` passes
6. Update CHANGELOG.md with your changes
7. Submit a PR against `master`

## Reporting Issues

- Use GitHub Issues for bug reports
- Include Python version, OS, and steps to reproduce
- Include relevant error messages or logs
