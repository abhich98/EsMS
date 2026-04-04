DATA_DIR := ./data
GENERATED_DATA_DIR := $(DATA_DIR)/generated
GROUND_TRUTH_FILE := $(DATA_DIR)/Dataset.xlsx

EXAMPLES_DIR := ./examples
BESS_FILE := $(EXAMPLES_DIR)/sample_BESS.json
RT_NOISE_PARAMS_FILE := $(EXAMPLES_DIR)/noise_params.yml

SCRIPTS_DIR := ./scripts
PYTHON := .venv/bin/python
STOC_OP_SCENARIOS := 9

export

.PHONY: app all

app: all
	$(PYTHON) -m streamlit run ./app/main.py

all: \
	$(GENERATED_DATA_DIR)/perfect_foresight_optimization_year.csv \
	$(GENERATED_DATA_DIR)/simulated_rt_prices_year.csv \
	$(GENERATED_DATA_DIR)/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv \
	$(GENERATED_DATA_DIR)/stochastic_policy_evaluation_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv

$(GENERATED_DATA_DIR)/perfect_foresight_optimization_year.csv: $(SCRIPTS_DIR)/deterministic_optimization.py $(GROUND_TRUTH_FILE) $(BESS_FILE)
	$(PYTHON) $< --data_file $(GROUND_TRUTH_FILE) --battery_file $(BESS_FILE) --start_day_index 0 --num_days 365 --output_file $@

$(GENERATED_DATA_DIR)/simulated_rt_prices_year.csv: $(SCRIPTS_DIR)/rt_price_simulation.py $(RT_NOISE_PARAMS_FILE) $(GROUND_TRUTH_FILE)
	$(PYTHON) $< --data_file $(GROUND_TRUTH_FILE) --noise_params_file $(RT_NOISE_PARAMS_FILE) --output_file $@

$(GENERATED_DATA_DIR)/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv: $(SCRIPTS_DIR)/stochastic_optimization.py $(GROUND_TRUTH_FILE) $(RT_NOISE_PARAMS_FILE) $(BESS_FILE)
	$(PYTHON) $< --data_file $(GROUND_TRUTH_FILE) --battery_file $(BESS_FILE) --noise_params_file $(RT_NOISE_PARAMS_FILE) --num_scenarios $(STOC_OP_SCENARIOS) --output_file $@

$(GENERATED_DATA_DIR)/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year_zero_noise.csv: $(SCRIPTS_DIR)/stochastic_optimization.py $(GROUND_TRUTH_FILE) $(EXAMPLES_DIR)/zero_noise_params.yml $(BESS_FILE)
	$(PYTHON) $< --data_file $(GROUND_TRUTH_FILE) --battery_file $(BESS_FILE) --noise_params_file $(EXAMPLES_DIR)/zero_noise_params.yml --num_scenarios $(STOC_OP_SCENARIOS) --output_file $@

$(GENERATED_DATA_DIR)/stochastic_policy_evaluation_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv: $(SCRIPTS_DIR)/stochastic_policy_evaluation.py $(GROUND_TRUTH_FILE) $(BESS_FILE) $(GENERATED_DATA_DIR)/simulated_rt_prices_year.csv $(GENERATED_DATA_DIR)/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv
	$(PYTHON) $< --data_file $(GROUND_TRUTH_FILE) --battery_file $(BESS_FILE) --policy_file $(GENERATED_DATA_DIR)/stochastic_optimization_with_$(STOC_OP_SCENARIOS)_scenarios_year.csv --rt_price_file $(GENERATED_DATA_DIR)/simulated_rt_prices_year.csv --start_day_index 0 --num_days 365 --output_file $@