CHECK_PYTHON := .venv-check/bin/python
LOCAL_PYTHON := .venv/bin/python
.PHONY: bootstrap setup-local doctor models dev run lint test test-browser test-gpu check check-docs check-security
bootstrap:
	./scripts/bootstrap.sh
setup-local:
	uv sync --locked --extra local --extra dev
models:
	$(LOCAL_PYTHON) model_setup.py
doctor:
	$(if $(wildcard $(LOCAL_PYTHON)),$(LOCAL_PYTHON),$(CHECK_PYTHON)) scripts/doctor.py
dev:
	npm run dev
run:
	npm run build
	./run.sh
lint:
	.venv-check/bin/ruff check .
	npm run lint
test:
	$(CHECK_PYTHON) -m pytest -q
	$(CHECK_PYTHON) -m unittest discover -s scripts -p 'test_*.py'
test-browser:
	$(CHECK_PYTHON) -m pytest -q tests/browser
check:
	./scripts/check.sh
check-docs:
	python3 scripts/docs_validation.py
	git diff --check
check-security:
	./scripts/security.sh
test-gpu:
	$(LOCAL_PYTHON) scripts/gpu_smoke.py --receipt .local/gpu-receipt.json

.PHONY: setup-mesh mesh-models test-mesh-backend
setup-mesh:
	./scripts/setup-mesh.sh
mesh-models:
	$(if $(wildcard $(LOCAL_PYTHON)),$(LOCAL_PYTHON),$(CHECK_PYTHON)) mesh_setup.py
test-mesh-backend:
	.venv-triposr/bin/python -m unittest discover -s backends/triposr -p 'test_*.py'

.PHONY: setup-rig rig-models
setup-rig:
	./scripts/setup-rig.sh
rig-models:
	$(if $(wildcard $(LOCAL_PYTHON)),$(LOCAL_PYTHON),$(CHECK_PYTHON)) rig_setup.py
