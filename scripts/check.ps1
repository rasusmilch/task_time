$ErrorActionPreference = "Stop"

python -m ruff format --check src tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m ruff check src tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m mypy src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m pytest -q
exit $LASTEXITCODE
