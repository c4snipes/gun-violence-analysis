.PHONY: fetch-education fetch-demographics split-cross-section diagnose-poverty install fetch fetch-saipe fetch-debt fetch-erpo fetch-mortality fetch-governors fetch-politics panel panel-analyze icc build analyze test lint all clean

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

fetch:
	$(PYTHON) scripts/fetch_mother_jones.py --out data/raw/mother_jones.csv

fetch-saipe:
	$(PYTHON) scripts/fetch_saipe.py --out data/raw/saipe_2014_2023.csv

fetch-debt:
	$(PYTHON) scripts/fetch_nyfed_debt.py --out data/nyfed_debt_2014_2023.csv

fetch-erpo:
	$(PYTHON) scripts/fetch_erpo_laws.py --out data/erpo_laws_2014_2023.csv

fetch-mortality:
	$(PYTHON) scripts/fetch_firearm_mortality_kff.py --out data/firearm_mortality_2014_2023.csv
	$(PYTHON) scripts/fetch_firearm_mortality.py --out data/firearm_mortality_2019_2024.csv

fetch-demographics:
	$(PYTHON) scripts/fetch_demographics.py --out data/demographics_2014_2023.csv

fetch-education:
	$(PYTHON) scripts/fetch_education_urbanicity.py --out data/education_2019_2023.csv --rural-out data/rurality_by_state.csv

fetch-governors:
	$(PYTHON) scripts/fetch_governors.py --out data/governors_2014_2023.csv

fetch-politics: fetch-governors
	$(PYTHON) scripts/fetch_state_politics.py --out data/state_politics_2014_2023.csv

# Every panel input. fetch-politics cross-checks itself against the governor
# panel, so it must run after it.
panel: fetch-saipe fetch-debt fetch-erpo fetch-mortality fetch-demographics fetch-education fetch-politics

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

split-cross-section:
	$(PYTHON) scripts/run_split_cross_section.py

diagnose-poverty:
	$(PYTHON) scripts/diagnose_poverty_within.py

panel-analyze: panel
	$(PYTHON) scripts/run_panel_analysis.py --out results/panel
