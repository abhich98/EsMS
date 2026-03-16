DATA_DIR = ./data
EXAMPLES_DIR = ./examples
SCRIPTS_DIR = ./scripts
PYTHON = .venv/bin/python

$(DATA_DIR)/generated/perfect_forecast_optimization_year.csv: $(SCRIPTS_DIR)/deterministic_optimisation.py $(DATA_DIR)/Dataset.xlsx $(EXAMPLES_DIR)/sample_BESS.json
	$(PYTHON) $(SCRIPTS_DIR)/deterministic_optimisation.py --data_file $(DATA_DIR)/Dataset.xlsx --battery_file $(EXAMPLES_DIR)/sample_BESS.json --start_day_index 0 --num_days 365 --output_file $@
