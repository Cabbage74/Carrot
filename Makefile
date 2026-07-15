lint:
	uv run ruff check .

fix:
	uv run ruff check --fix .

test:
	uv run pytest -q

audit:
	uv run python -m audit.run_audit

eval-selftest:
	uv run python -m evals.run_evals --self-test

eval:
	uv run python -m evals.run_evals
