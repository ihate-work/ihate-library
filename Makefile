PYTHON_VER ?= 3.13
UV_PIP_INSTALL = UV_PYTHON=.venv uv pip install

.PHONY: setup sync format typecheck test clean

setup: .venv/.deps_installed

.venv/.venv_created:
	uv venv --python $(PYTHON_VER) .venv
	@touch $@

.venv/.deps_installed: .venv/.venv_created pyproject.toml requirements.txt
	$(UV_PIP_INSTALL) -r requirements.txt --editable .
	@touch $@

sync: .venv/.venv_created
	$(UV_PIP_INSTALL) -r requirements.txt --editable .
	@touch .venv/.deps_installed

format:
	npx dprint fmt .

typecheck:
	.venv/bin/mypy src

test:
	.venv/bin/pytest

clean:
	rm -rf .venv __pycache__ .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
