$ErrorActionPreference = "Stop"

python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy src
