from venv import logger

import pandas as pd
import numpy as np
import argparse
import logging
import yaml
from joblib import Parallel, delayed

from esms.utils import simulate_rt_prices


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def main():
    parser = argparse.ArgumentParser(description='Simulate Real-Time prices from Day-Ahead prices.')
    parser.add_argument('--data_file', type=str, required=True, help='Path to the Day-Ahead prices Excel file')
    parser.add_argument('--noise_params_file', type=str, required=True, help='Path to the noise parameters YAML file')
    parser.add_argument('--output_path', type=str, required=True, help='Path to save the simulated Real-Time prices CSV file')
    args = parser.parse_args()

    logging.info("Loading Day-Ahead prices from %s", args.data_file)
    data_df = pd.read_excel(args.data_file, sheet_name='2023 data', usecols='A:F', nrows=8762)
    da_prices_df = data_df[['Date', 'Energy price (EUR/kWh)']].copy()
    da_prices_df.rename(columns={'Date': 'timestamp', 'Energy price (EUR/kWh)': 'price'}, inplace=True)

    noise_params = yaml.safe_load(open(args.noise_params_file))
    volatility_range = noise_params['volatility_range']
    jump_prob = noise_params['jump_prob']
    jump_magnitude_range = noise_params['jump_magnitude_range']

    num_days = len(da_prices_df) // 24

    volatility_values = np.random.uniform(*volatility_range, size=num_days)
    jump_magnitude_values = np.random.uniform(*jump_magnitude_range, size=num_days)

    logging.info("Simulating Real-Time prices...")
    rt_prices_df = Parallel(n_jobs=-1)(
        delayed(simulate_rt_prices)(
            da_prices_df[i*24:(i+1)*24],
            volatility_values[i],
            jump_prob,
            jump_magnitude_values[i]
            ) for i in range(num_days))
    
    rt_prices_df = pd.concat(rt_prices_df, ignore_index=True)
    rt_prices_df.rename(columns={'timestamp': 'Date', 
                                 'rt_price': 'RT energy price (EUR/kWh)'}, inplace=True)
    rt_prices_df.sort_values('Date', inplace=True)

    logging.info("Saving simulated Real-Time prices to %s", args.output_path)
    rt_prices_df.to_csv(args.output_path, index=False)


if __name__ == "__main__":
    main()