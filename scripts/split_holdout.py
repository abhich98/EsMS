from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
import yaml

from household_battery.split import make_noncontiguous_holdout, persist_split


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create a seeded non-contiguous backtest/holdout split of the data"
    )
    p.add_argument(
        "--data_file", type=Path, required=True, help="Path to the dataset Excel file"
    )
    p.add_argument("--year", type=int, default=2025)
    p.add_argument(
        "--config_file",
        type=Path,
        required=True,
        help="Path to the YAML file specifying the split configuration",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    data_df = pd.read_excel(
        args.data_file, sheet_name=f"{args.year} data", usecols="A:F"
    )
    data_df["Date"] = pd.to_datetime(data_df["Date"])

    with args.config_file.open("r") as f:
        split_config = yaml.safe_load(f)

    dates = pd.to_datetime(data_df["Date"]).dt.date.unique()
    dates = pd.to_datetime(dates).sort_values()
    # dates = pd.Series(dates).sort_values(ignore_index=True)

    holdout, backtest = make_noncontiguous_holdout(
        dates=dates[
            split_config["start_day_index"] : split_config["start_day_index"]
            + split_config["num_days"]
        ],
        holdout_days=split_config["holdout_days"],
        seed=split_config["random_seed"],
    )
    persist_split(holdout, backtest, str(split_config["output"]["directory"]))


if __name__ == "__main__":
    main()
