DATA_DIR = ./data
EXAMPLES_DIR = ./examples
SCRIPTS_DIR = ./scripts
PYTHON = .venv/bin/python
STOC_OP_SCENARIOS = 9

.PHONY: all

all: \
	$(DATA_DIR)/generated/perfect_foresight_optimization_year.csv \
	$(DATA_DIR)/generated/simulated_rt_prices_year.csv \
	$(DATA_DIR)/generated/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv \
	$(DATA_DIR)/generated/stochastic_policy_evaluation_year.csv

$(DATA_DIR)/generated/perfect_foresight_optimization_year.csv: $(SCRIPTS_DIR)/deterministic_optimization.py $(DATA_DIR)/Dataset.xlsx $(EXAMPLES_DIR)/sample_BESS.json
	$(PYTHON) $< --data_file $(DATA_DIR)/Dataset.xlsx --battery_file $(EXAMPLES_DIR)/sample_BESS.json --start_day_index 0 --num_days 365 --output_file $@

$(DATA_DIR)/generated/simulated_rt_prices_year.csv: $(SCRIPTS_DIR)/rt_price_simulation.py $(EXAMPLES_DIR)/noise_params.yml $(DATA_DIR)/Dataset.xlsx
	$(PYTHON) $< --data_file $(DATA_DIR)/Dataset.xlsx --noise_params_file $(EXAMPLES_DIR)/noise_params.yml --output_file $@

$(DATA_DIR)/generated/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv: $(SCRIPTS_DIR)/stochastic_optimization.py $(DATA_DIR)/Dataset.xlsx $(EXAMPLES_DIR)/noise_params.yml $(EXAMPLES_DIR)/sample_BESS.json
	$(PYTHON) $< --data_file $(DATA_DIR)/Dataset.xlsx --battery_file $(EXAMPLES_DIR)/sample_BESS.json --noise_params_file $(EXAMPLES_DIR)/noise_params.yml --num_scenarios $(STOC_OP_SCENARIOS) --output_file $@

$(DATA_DIR)/generated/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year_zero_noise.csv: $(SCRIPTS_DIR)/stochastic_optimization.py $(DATA_DIR)/Dataset.xlsx $(EXAMPLES_DIR)/zero_noise_params.yml $(EXAMPLES_DIR)/sample_BESS.json
	$(PYTHON) $< --data_file $(DATA_DIR)/Dataset.xlsx --battery_file $(EXAMPLES_DIR)/sample_BESS.json --noise_params_file $(EXAMPLES_DIR)/zero_noise_params.yml --num_scenarios $(STOC_OP_SCENARIOS) --output_file $@

$(DATA_DIR)/generated/stochastic_policy_evaluation_year.csv: $(SCRIPTS_DIR)/stochastic_policy_evaluation.py $(DATA_DIR)/Dataset.xlsx $(EXAMPLES_DIR)/sample_BESS.json $(DATA_DIR)/generated/simulated_rt_prices_year.csv $(DATA_DIR)/generated/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv
	$(PYTHON) $< --data_file $(DATA_DIR)/Dataset.xlsx --battery_file $(EXAMPLES_DIR)/sample_BESS.json --policy_file $(DATA_DIR)/generated/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv --rt_price_file $(DATA_DIR)/generated/simulated_rt_prices_year.csv --start_day_index 0 --num_days 365 --output_file $@