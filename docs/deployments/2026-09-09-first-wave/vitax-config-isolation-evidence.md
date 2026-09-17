# VitaX VX004 config env-loading evidence

Generated: 2026-09-09
Workspace: `/Users/hai/Projects/ohpc-migration/VitaX`

## Early omitted-switch command

The exact command was:

```sh
.venv/bin/python -m pytest tests/unit/test_config_env_loading.py tests/unit/test_config_base_dir_override.py tests/unit/kb/test_config.py -q
```

It did not prefix `OMNIGRAPH_LOAD_ENV=0`.

The command selected 16 tests. The only selected tests that can import root
`config.py` using the real process home are these four in
`tests/unit/test_config_base_dir_override.py`:

1. `test_env_unset_defaults_to_hermes`
2. `test_env_empty_string_falls_back_to_default`
3. `test_env_set_absolute_path_wins`
4. `test_dependent_paths_inherit`

They call `_run_config_print()`, which starts a subprocess with `cwd` at the
repository root and inherits the parent environment. Before VX004, this could
consult `~/.hermes/.env`; this evidence did not inspect that file or print its
contents.

`tests/unit/test_config_env_loading.py` instead patches `Path.home()` to
pytest's `tmp_path`. `tests/unit/kb/test_config.py` reloads `kb.config`, which
reads environment variables only and does not import root `config.py`.

## TDD commands and observed results

RED command:

```sh
.venv/bin/python -m pytest tests/unit/test_config_env_loading.py -q
```

Observed result before the code change: `2 failed, 2 passed`. Failures were
`test_zero_disables_env_file_checks_for_import_and_explicit_load` and
`test_invalid_env_loading_switch_fails_closed`.

GREEN command:

```sh
.venv/bin/python -m pytest tests/unit/test_config_env_loading.py -q
```

Observed result after the code change: `4 passed`.

Final isolated verification command:

```sh
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest tests/unit/test_config_env_loading.py tests/unit/test_config_base_dir_override.py tests/unit/kb/test_config.py -q
```

Observed result: `16 passed in 0.16s`.

## Actual final test list

```text
tests/unit/test_config_env_loading.py::test_default_loads_env_file_from_isolated_home
tests/unit/test_config_env_loading.py::test_zero_disables_env_file_checks_for_import_and_explicit_load
tests/unit/test_config_env_loading.py::test_existing_environment_value_is_not_overwritten
tests/unit/test_config_env_loading.py::test_invalid_env_loading_switch_fails_closed
tests/unit/test_config_base_dir_override.py::test_env_unset_defaults_to_hermes
tests/unit/test_config_base_dir_override.py::test_env_empty_string_falls_back_to_default
tests/unit/test_config_base_dir_override.py::test_env_set_absolute_path_wins
tests/unit/test_config_base_dir_override.py::test_dependent_paths_inherit
tests/unit/kb/test_config.py::test_kb_db_path_default
tests/unit/kb/test_config.py::test_kb_db_path_env_override
tests/unit/kb/test_config.py::test_kb_images_dir_default
tests/unit/kb/test_config.py::test_kb_output_dir_default
tests/unit/kb/test_config.py::test_kb_port_default_and_env_override
tests/unit/kb/test_config.py::test_kb_default_lang_default
tests/unit/kb/test_config.py::test_kb_synthesize_timeout_default
tests/unit/kb/test_config.py::test_all_constants_re_read_env_on_reload
```

Collected with:

```sh
OMNIGRAPH_LOAD_ENV=0 .venv/bin/python -m pytest --collect-only -q tests/unit/test_config_env_loading.py tests/unit/test_config_base_dir_override.py tests/unit/kb/test_config.py
```

## Static side-effect review

No test was rerun for this review, and no `.env` was read or printed.

- Network: no selected test, `config.py`, or `kb/config.py` invokes a network
  client. The selected subprocesses run only `import config; print(config.<path
  attribute>)`.
- Runtime/home persistent data: with `OMNIGRAPH_LOAD_ENV=0`, root `load_env()`
  returns before `exists()` or `open()`. The selected tests do not write the
  Hermes runtime tree or production databases.
- Temporary writes: `test_config_env_loading.py` creates a fake `.env` below
  pytest `tmp_path`; `test_config_base_dir_override.py` creates target folders
  below `tmp_path`. The session-autouse fixture in `tests/conftest.py` creates
  an `ogv-vision-ckpt-*` directory using `tempfile.mkdtemp()` and does not
  remove that directory itself. Standard pytest/Python cache artifacts may
  also be created by the runner. These are test-harness filesystem writes,
  not network calls or Hermes runtime writes.
