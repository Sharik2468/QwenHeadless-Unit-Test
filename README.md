# QwenHeadless-Unit-Test

Python orchestration script for generating and maintaining Avalonia UIKit unit/headless tests with Qwen Code headless.

## What it does

- recursively discovers candidate controls from a styles root
- optionally matches custom control `.cs` files from a separate source root
- writes a control manifest for repeatable processing
- runs one Qwen headless session per control
- asks Qwen to generate or update unit/headless tests
- runs `dotnet build` and `dotnet test` after each control
- retries failed controls with repair prompts
- persists run state so the pipeline can be resumed later
- rechecks previously generated tests on repeated runs

## Commands

If your repository matches the NSCore UIKit Avalonia layout shown below, the script can auto-detect these paths from `--repo-root`:

- `Avalonia/NSCore.UIKit.Controls.UnitTests/NSCore.UIKit.Controls.UnitTests.csproj`
- `Avalonia/NSCore.UIKit.Headless.XUnit.UnitTests/NSCore.UIKit.Headless.XUnit.UnitTests.csproj`
- `Avalonia/NSCore.Avalonia.Theme/Controls`

### Discover controls

```bash
python3 generate_uikit_tests.py discover \
  --repo-root /repo \
  --artifacts-dir /repo/.uikit-testgen-artifacts
```

### Run end-to-end orchestration

```bash
python3 generate_uikit_tests.py run \
  --repo-root /repo \
  --artifacts-dir /repo/.uikit-testgen-artifacts \
  --model qwen3-coder-plus \
  --max-repair-attempts 3
```

### Resume interrupted work

```bash
python3 generate_uikit_tests.py resume \
  --repo-root /repo \
  --artifacts-dir /repo/.uikit-testgen-artifacts
```

### Recheck existing tests

```bash
python3 generate_uikit_tests.py recheck \
  --repo-root /repo \
  --artifacts-dir /repo/.uikit-testgen-artifacts
```

## Artifacts

The script writes:

- `controls_manifest.json`
- `progress.json`
- per-control prompts, Qwen outputs, build/test logs, and `result.json`

under the configured `artifacts-dir`.

## Local verification

```bash
python3 -m unittest discover -s tests -v
```

## Generic project unit-test orchestrator

This repository also includes a second CLI for classic unit tests in one specific .NET source project:

- plan likely unit-test candidates for one source project
- pick realistic candidates in repository-owned code
- implement unit tests in an existing test project
- build and run tests after each candidate
- retry failed candidates with repair prompts

### Plan candidates

```bash
python3 generate_project_unit_tests.py plan \
  --repo-root /repo \
  --source-project /repo/src/MyProduct/MyProduct.csproj \
  --test-project /repo/tests/MyProduct.UnitTests/MyProduct.UnitTests.csproj \
  --artifacts-dir /repo/.project-unit-testgen-artifacts
```

### Run planning + implementation

```bash
python3 generate_project_unit_tests.py run \
  --repo-root /repo \
  --source-project /repo/src/MyProduct/MyProduct.csproj \
  --test-project /repo/tests/MyProduct.UnitTests/MyProduct.UnitTests.csproj \
  --artifacts-dir /repo/.project-unit-testgen-artifacts
```

### Resume interrupted run

```bash
python3 generate_project_unit_tests.py resume \
  --repo-root /repo \
  --source-project /repo/src/MyProduct/MyProduct.csproj \
  --test-project /repo/tests/MyProduct.UnitTests/MyProduct.UnitTests.csproj \
  --artifacts-dir /repo/.project-unit-testgen-artifacts
```

If `--test-project` is omitted, the script tries to auto-detect a matching `*.Tests` or `*.UnitTests` project inside the repository.
