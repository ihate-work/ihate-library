PYTHON_VER ?= 3.13

REQUIREMENTS_RUNTIME = -r requirements.txt
REQUIREMENTS_DEV = -r requirements-dev.txt -r requirements.txt

UV_PIP_INSTALL = UV_PYTHON=.venv uv pip install

.PHONY: setup sync format typecheck test clean

default: runtime-deps

# Dev deps (runtime + test/lint tools)
deps: .venv/.dev_deps_installed

# Runtime-only deps
runtime-deps: .venv/.deps_installed

.venv/.venv_created: Makefile
	uv venv --python $(PYTHON_VER) .venv
	@touch $@
	@rm -fv .venv/.deps_installed .venv/.dev_deps_installed

.venv/.deps_installed: .venv/.venv_created pyproject.toml requirements.txt
	$(UV_PIP_INSTALL) $(REQUIREMENTS_RUNTIME)
	@echo "runtime deps installed"
	@touch $@

.venv/.dev_deps_installed: .venv/.venv_created pyproject.toml requirements.txt requirements-dev.txt
	$(UV_PIP_INSTALL) $(REQUIREMENTS_DEV)
	@echo "dev deps installed"
	@touch $@

sync: .venv/.venv_created
	$(UV_PIP_INSTALL) $(REQUIREMENTS_DEV)
	@touch .venv/.dev_deps_installed

format:
	npx dprint fmt .

typecheck: deps
	.venv/bin/mypy src

test: deps
	.venv/bin/pytest

clean:
	rm -rf .venv __pycache__ .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
