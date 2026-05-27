.PHONY: install test lint format run-lab1-vector run-lab1-raster benchmark

install:
	pip install -e ".[dev]" --break-system-packages

test:
	pytest tests/

lint:
	ruff check src/ examples/
	black --check src/ examples/

format:
	black src/ examples/
	ruff check --fix src/ examples/

run-lab1-vector:
	python3 examples/lab1_vector.py run \
		-t examples/model.toml \
		--input examples/data/input/csAC.zip \
		--param demand_csv=examples/data/input/examples_demand_lab1.csv \
		--param interactive=True

run-lab1-raster:
	python3 examples/lab1_raster.py run \
		-t examples/model.toml \
		--input examples/data/input/csAC.zip \
		--param demand_csv=examples/data/input/examples_demand_lab1.csv \
		--param interactive=True \
		--param n_steps=7

benchmark:
	python3 -m disslucc_continuous.infra.executors.lucc_benchmark_executor run \
		--input  examples/data/input/csAC.zip \
		--output ./benchmark/results/ \
		--param  demand_csv=examples/data/input/examples_demand_lab1.csv \
		--param  terrame_reference=benchmark/data/LUCCME_Lab1_2014.zip \
		--param  n_steps=6 \
		--param  tolerance=0.01
