#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "boto3>=1.39.10",
#   "plotext>=5.2.8",
# ]
# ///

"""aws-spot-pricing

Fetch AWS EC2 Spot Price history and calculate basic statistics.

Example usage:

    uv run --script main.py --region us-east-1 --instance-type m5.large --hours 12
"""

from __future__ import annotations

import argparse
import statistics
from datetime import datetime, timedelta, timezone
from typing import List

import boto3
import plotext as plt



def fetch_spot_prices(
    *,
    region: str,
    instance_type: str,
    start_time: datetime,
    end_time: datetime,
    product_description: str,
) -> tuple[list[datetime], list[float]]:
    ec2 = boto3.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_spot_price_history")

    timestamps: list[datetime] = []
    prices: list[float] = []
    for page in paginator.paginate(
        StartTime=start_time,
        EndTime=end_time,
        InstanceTypes=[instance_type],
        ProductDescriptions=[product_description],
    ):
        for entry in page.get("SpotPriceHistory", []):
            try:
                prices.append(float(entry["SpotPrice"]))
                # AWS returns timezone-aware datetime objects (UTC)
                timestamps.append(entry["Timestamp"].replace(tzinfo=timezone.utc))
            except (KeyError, ValueError):
                continue

    # Sort by timestamp ascending (oldest first)
    if timestamps:
        combined = sorted(zip(timestamps, prices), key=lambda t: t[0])
        timestamps, prices = map(list, zip(*combined))

    return timestamps, prices


def compute_stats(prices: List[float]) -> dict:
    return {
        "samples": len(prices),
        "min": min(prices),
        "max": max(prices),
        "mean": statistics.mean(prices),
        "median": statistics.median(prices),
        "stdev": statistics.pstdev(prices) if len(prices) > 1 else 0.0,
    }


def plot_price_history(timestamps: list[datetime], prices: list[float]) -> None:
    # Convert timestamps to hours ago from the most recent timestamp, keeping chronological order
    end_timestamp = timestamps[-1]
    x_hours_ago = [(end_timestamp - ts).total_seconds() / 3600 for ts in timestamps]
    
    # Calculate statistics for reference lines
    mean_price = statistics.mean(prices)
    median_price = statistics.median(prices)
    
    start_time = timestamps[0].strftime("%m-%d %H:%M")
    end_time = timestamps[-1].strftime("%m-%d %H:%M")
    title = f"AWS Spot Price History ({start_time} to {end_time} UTC) \nMean: ${mean_price:.6f} \nMedian: ${median_price:.6f}"
    
    plt.plot(x_hours_ago, prices, marker="$", label="USD/hr", color="green")
    plt.hline(mean_price, color="red")
    plt.hline(median_price, color="blue")
    plt.title(title)
    plt.xlabel("Hours ago")
    plt.ylabel("Price (USD/hr)")
    plt.plotsize(100, 30)  # width, height in characters
    plt.show()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch AWS Spot Price history and compute basic statistics.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="""
Examples:
  %(prog)s --region us-east-1 --instance-type m5.large --hours 12
  %(prog)s --region us-west-2 --instance-type c5.xlarge --hours 24 --product-description "Linux/UNIX (Amazon VPC)"
        """,
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region to query (default: %(default)s)",
    )
    parser.add_argument(
        "--instance-type",
        default="m5.large",
        help="EC2 instance type to query (default: %(default)s)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=2160, # 3 months
        help="Number of hours in the past to include in the query window (default: %(default)s)",
    )
    parser.add_argument(
        "--product-description",
        default="Linux/UNIX (Amazon VPC)",
        choices=["Linux/UNIX", "Linux/UNIX (Amazon VPC)", "Windows", "Windows (Amazon VPC)"],
        help="Product description filter (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""

    args = parse_args()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=args.hours)

    print(f"Fetching spot price history for {args.instance_type} in {args.region}...")
    print(f"Time window: {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()

    timestamps, prices = fetch_spot_prices(
            region=args.region,
            instance_type=args.instance_type,
            start_time=start_time,
            end_time=end_time,
            product_description=args.product_description,
        )

    if not prices:
        raise RuntimeError("No spot price data found for the specified parameters. Try adjusting the time window or instance type.")

    stats = compute_stats(prices)

    print(f"📊 Statistics for {args.instance_type} in {args.region}")
    print(f"   Product: {args.product_description}")
    print(f"   Time range: {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("-" * 70)
    print(f"📈 Samples          : {stats['samples']:,}")
    print(f"💰 Minimum (USD/hr) : ${stats['min']:.6f}")
    print(f"💰 Maximum (USD/hr) : ${stats['max']:.6f}")
    print(f"📊 Mean    (USD/hr) : ${stats['mean']:.6f}")
    print(f"📊 Median  (USD/hr) : ${stats['median']:.6f}")
    print(f"📊 StdDev  (USD/hr) : ${stats['stdev']:.6f}")
    print()

    plot_price_history(timestamps, prices)


if __name__ == "__main__":
    main()
