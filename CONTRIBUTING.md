# Contributing to ValetudoVoicing

Thank you for your interest in contributing to **ValetudoVoicing**!

## Development Setup

```bash
git clone https://github.com/smilebob/ValetudoVoicing.git
cd ValetudoVoicing
uv sync --extra dev
uv run pytest -v
```

## Guidelines

- Keep functions small, focused, and well-typed.
- Add unit tests in `tests/` for any new CLI commands, audio effects, or packaging logic.
- Ensure all existing tests pass (`uv run pytest -v`) before opening a Pull Request.
- By contributing, you agree that your contributions will be licensed under the **Apache-2.0** License.
