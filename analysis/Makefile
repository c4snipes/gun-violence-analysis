.PHONY: install fetch fetch-saipe fetch-debt fetch-governors fetch-politics panel icc build analyze test lint all clean

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

fetch:
	$(PYTHON) scripts/fetch_mother_jones.py --out data/raw/mother_jones.csv

fetch-saipe:
	$(PYTHON) scripts/fetch_saipe.py --out data/raw/saipe_2014_2023.csv

fetch-debt:
	$(PYTHON) scripts/fetch_nyfed_debt.py --out data/nyfed_debt_2014_2023.csv

fetch-governors:
	$(PYTHON) scripts/fetch_governors.py --out data/governors_2014_2023.csv

fetch-politics: fetch-governors
	$(PYTHON) scripts/fetch_state_politics.py --out data/state_politics_2014_2023.csv

# Every panel input. fetch-politics cross-checks itself against the governor
# panel, so it must run after it.
panel: fetch-saipe fetch-debt fetch-politics

icc: fetch-saipe
	$(PYTHON) scripts/measure_icc.py --saipe data/raw/saipe_2014_2023.csv

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
