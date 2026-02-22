# AGENTS.md

## Purpose
- This file guides autonomous coding agents working in this repository.
- Prefer repository conventions over generic defaults.
- Keep edits minimal, scoped, and backed by tests.

## Repository Snapshot
- Language: Python.
- Runtime requirement: Python >= 3.14 (`pyproject.toml`).
- Packaging backend: setuptools (`setuptools.build_meta`).
- Source root: `src/image_harvester/`.
- Test root: `tests/`.
- Main entrypoint: `harvester-tui` and `python -m image_harvester`.
- Core persistence: SQLite via `StateStore`.
- Runtime output/state directory: `data/` (gitignored).

## Setup Commands
- Create and activate a virtual environment before development.
- Install base package: `python -m pip install -e .`
- Install TUI dependency: `python -m pip install -e ".[tui]"`
- Install Playwright support: `python -m pip install -e ".[playwright]"` then `playwright install chromium`
- Install test/dev dependencies: `python -m pip install -e ".[dev]"`
- Typical full local setup: `python -m pip install -e ".[tui,playwright,dev]"`

## Build and Run Commands
- Editable build/install: `python -m pip install -e .`
- Package build validation: `python -m pip install build` then `python -m build`
- Run app via module: `python -m image_harvester`
- Run app via console script: `harvester-tui`

## Lint and Static Analysis
- There is no repo-configured linter command in `pyproject.toml`.
- There is no repo-configured type-check command in `pyproject.toml`.
- Do not assume Ruff/Black/Flake8/isort/mypy/pyright are installed.
- Quick syntax sanity check: `python -m compileall src tests`
- If lint/type tooling is added, also add commands to `pyproject.toml` and this file.

## Test Commands
- Test runner: `pytest`.
- Test config: `[tool.pytest.ini_options]` in `pyproject.toml`.
- Run full suite: `pytest`
- Run one test file: `pytest tests/test_config.py`
- Run one specific test: `pytest tests/test_config.py::test_build_run_config_sets_sequence_defaults`
- Run by keyword: `pytest -k "sequence and not probe"`
- Stop on first failure: `pytest -x`
- Quiet targeted run: `pytest -q tests/test_tui_worker.py::test_worker_runs_pipeline_to_completed`

## Architecture Guide
- `models.py`: shared dataclasses and typed records.
- `config.py`: config loading/normalization/validation and job-id serialization.
- `fetchers/`: fetcher interface plus requests/playwright implementations.
- `downloader.py`: image download, retries, and adaptive rate limiting.
- `pipeline.py`: end-to-end orchestration, sequencing, metadata, retry flow.
- `state.py`: SQLite persistence for jobs/pages/images/events.
- `tui/forms.py`: run config payload conversion and form validation.
- `tui/services.py`: background worker and snapshot read model.
- `tui/widgets.py`: Textual tables and summary panel widgets.

## Code Style Rules

### Imports
- Order imports as: standard library, third-party, local package.
- Separate import groups with one blank line.
- Prefer explicit imports; avoid wildcard imports.
- Follow existing relative-import pattern inside package modules.

### Formatting
- Use 4-space indentation.
- Use double quotes consistently.
- Keep trailing commas in multiline literals/calls when surrounding code does.
- Keep docstrings concise; most modules and public functions already have them.
- Prefer readable vertical wrapping for long calls and literals.

### Types
- Keep `from __future__ import annotations` at the top of modules.
- Annotate function parameters and return types (`-> None` included).
- Use built-in generics (`list[str]`, `dict[str, Any]`, etc.).
- Use `X | None` unions (not `Optional[X]`) to match project style.
- Use `@dataclass(slots=True)` for shared records when adding new dataclasses.

### Naming
- `snake_case` for functions, variables, and methods.
- `PascalCase` for classes.
- `UPPER_CASE` for constants (example: `FORM_DEFAULTS`).
- Prefix private helpers with `_`.
- Name tests as `test_<behavior>` in `test_*.py` files.

### Error Handling
- Validate inputs early; raise clear `ValueError` or `FileNotFoundError` messages.
- Keep user-facing message style consistent with existing code and tests.
- At integration boundaries, convert failures into structured results when possible.
- In pipeline flows, persist failure context through `StateStore` and events.
- Use broad `except Exception` only at boundaries that must not crash silently.
- Never swallow exceptions unless in safe cleanup paths.

### I/O and Persistence
- Use `pathlib.Path` for filesystem paths.
- Ensure parent directories exist before writing files.
- Keep JSON writes atomic (write temp file, then replace).
- Use UTF-8 for text I/O.
- Route DB state transitions through `StateStore` methods.

### Concurrency and Retries
- Respect `RunConfig` knobs for workers, retries, delays, and backoff.
- Keep shared mutable state thread-safe; existing locks/executors are intentional.
- Avoid introducing global mutable state.
- Keep retry behavior deterministic in tests via fake downloader/fetcher classes.

### Testing Practices
- Prefer deterministic tests with fake fetchers and fake downloaders.
- Use `workspace_temp_dir` fixture for filesystem isolation.
- Avoid real network calls in tests.
- Update/add tests for config, pipeline, state, and TUI service changes.
- Be careful changing exception text; several tests assert exact message content.

## Change Scope and Safety
- Read nearby code before editing; follow local patterns.
- Keep diffs focused; avoid unrelated refactors.
- Preserve behavior unless the task explicitly requests a behavior change.
- Avoid introducing new dependencies without clear need.
- Avoid touching runtime artifacts under `data/`.
- Do not commit temporary test directories or generated local state.

## When to Run Full Pytest
- Run targeted tests first for files you changed.
- Run full `pytest` when changing shared pipeline/state/config logic.
- Run full `pytest` when changing behavior used by both CLI/TUI paths.
- If a targeted test fails due to nearby behavior, expand test scope before finishing.

## Cursor and Copilot Rules Status
- `.cursorrules`: not present.
- `.cursor/rules/`: not present.
- `.github/copilot-instructions.md`: not present.
- If any are added later, treat them as higher-priority instructions and merge here.

## Agent Workflow Checklist
- Read this file and nearby code before making edits.
- Follow existing naming, typing, and error-message patterns.
- Add or update tests with behavioral code changes.
- Prefer targeted tests first, then broader tests as needed.
- Keep output concise and include file paths changed.
- Update this file when adding new build/lint/test commands or conventions.
