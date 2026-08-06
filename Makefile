.PHONY: install fetch build analyze test lint all clean

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

fetch:
	$(PYTHON) scripts/fetch_mother_jones.py --out data/raw/mother_jones.csv

build:
	$(PYTHON) scripts/build_dataset.py \
		--sri-workbook data/raw/SnipesCFinalDataAnalysis.xlsx \
		--mother-jones data/raw/mother_jones.csv \
		--out data/state_data_full.csv

analyze:
	$(PYTHON) scripts/run_analysis.py \
		--data data/state_data_full.csv \
		--figures figures \
		--results results

test:
	$(PYTHON) -m pytest -v

lint:
	ruff check src tests scripts

all: fetch build analyze

clean:
	rm -rf figures results data/state_data_full.csv data/raw/mother_jones.csv
	find . -type d -name __pycache__ -exec rm -rf {} +
