#!/usr/bin/env python3
import csv
from multiprocessing import Pool
import os
import subprocess
from datetime import datetime, timedelta

DEFAULT_SINGLE_FILE = "/home/j/.nvm/versions/node/v20.18.2/bin/single-file"
DEFAULT_CSV_FILE = "_site/archive.csv"
DEFAULT_OUT_DIR = "crawl_sites"
DEFAULT_THREADS = 3
DEFAULT_SUBSET = 0
DEFAULT_BROWSER_WAIT_DELAY = "40000"  # 40 seconds

# set up logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def process_links(csv_file, out_dir, single_file, subset):
    with open(csv_file, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        rows = [row for row in reader]

        logger.info(f"Found {len(rows)} total rows in the CSV file.")

        # Remove all invalid rows
        rows = [row for row in rows if row["invalid"] != "true"]
        logger.info(f"Found {len(rows)} valid rows in the CSV file.")

        # Remove all rows with a url that matches a list of patterns
        patterns = [
            "www.youtube.com",
            "play.google.com",
            "maps.black",
            "irenedelatorre.github.io/30DayMapChallenge",
            "ecodatacube.eu?base=OpenStreetMap",
        ]
        for pattern in patterns:
            rows = [row for row in rows if pattern not in row["link"]]
        logger.info(
            f"Found {len(rows)} rows and {len(rows)} rows after filtering excluded patterns."
        )

        # Randomly select a subset of rows to process
        if subset > 0:
            import random

            random.seed(42)  # For reproducibility
            random.shuffle(rows)
            if subset > len(rows):
                print(
                    f"Subset size {subset} is larger than the number of commands {len(rows)}. Adjusting to {len(rows)}."
                )
                subset = len(rows)
            rows = rows[:subset]

        commands = []
        for row in rows:
            date_str = row["date"]
            id_ = row["id"]
            url = row["link"]

            # Skip empty or invalid URL
            if not url:
                logger.error(f"Empty URL for ID: {id_}")
                raise ValueError(f"Empty URL for ID: {id_}")
            if not url.startswith("http://") and not url.startswith("https://"):
                logger.error(f"Invalid URL: {url}")
                raise ValueError(f"Invalid URL: {url}")

            # Convert ISO full date and time with timezone string into YYYY-MM-DD
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                try:
                    date_obj = datetime.strptime(date_str, "%Y/%m/%d")
                except ValueError:
                    logger.error(f"Invalid date format: {date_str}")
                    raise ValueError(f"Invalid date format: {date_str}")
            date_fmt = date_obj.strftime("%Y-%m-%d")
            date_year = date_obj.strftime("%Y")
            date_month = date_obj.strftime("%m")

            # Get the base domain from the URL
            base_domain = url.split("/")[2] if "://" in url else url.split("/")[0]

            # Create a reproducible filename from the date, id, and base domain
            basename = f"{date_fmt}-{id_}-{base_domain}"

            # Try to find a file with the basename and any extension
            out_date_dir = os.path.join(out_dir, date_year, date_month)
            file_exsits = False

            # walk the directory tree to find the file
            for root, _, files in os.walk(out_date_dir):
                for file in files:
                    if file.startswith(basename):
                        file_exsits = True
                        break
            if file_exsits:
                logger.debug(
                    f"File {basename} already exists at {out_date_dir}, skipping download."
                )
            else:
                logger.debug(
                    f"File {basename} does not exist, it will be downloaded at {out_date_dir}"
                )

                # Build single-file command
                commands.append(
                    [
                        single_file,
                        "--dump-content=false",
                        "--browser-wait-delay",
                        DEFAULT_BROWSER_WAIT_DELAY,
                        "--output-directory",
                        out_date_dir,
                        "--filename-template",
                        f'"{basename}.{{filename-extension}}"',
                        f'"{url}"',
                    ]
                )

        return commands


if __name__ == "__main__":
    # Accept the CSV file to process as a command-line argument
    import argparse

    parser = argparse.ArgumentParser(
        description="Process URLs from a CSV file into single files."
    )
    parser.add_argument(
        "--csv-file",
        help="Path to the CSV file containing URLs.",
        default=DEFAULT_CSV_FILE,
    )
    parser.add_argument(
        "--out-dir", help="Output directory for saved files.", default=DEFAULT_OUT_DIR
    )
    parser.add_argument(
        "--threads", type=int, help="Number of threads to use.", default=DEFAULT_THREADS
    )
    parser.add_argument(
        "--single-file",
        help="Path to the single-file executable.",
        default=DEFAULT_SINGLE_FILE,
    )
    parser.add_argument(
        "--log-level",
        help="Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
        default="INFO",
    )
    parser.add_argument(
        "--subset",
        type=int,
        help="Randomly select a subset of rows to process.",
        default=DEFAULT_SUBSET,
    )
    args = parser.parse_args()

    logger.setLevel(args.log_level.upper())

    CSV_FILE = args.csv_file
    OUT_DIR = args.out_dir
    THREADS = args.threads
    SINGLE_FILE = args.single_file
    SUBSET = args.subset

    commands = process_links(CSV_FILE, OUT_DIR, SINGLE_FILE, SUBSET)
    commands_str = [" ".join(cmd) for cmd in commands]

    logger.info(f"{len(commands)} commands to run in {THREADS} processes.")

    # Read past failed commands from a CSV file with the command and date
    checked_urls_file = "crawl_sites/checked_urls.csv"
    checked_urls = []
    if os.path.exists(checked_urls_file):
        with open(checked_urls_file, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                checked_urls.append(row)

    # Get a date object for one month ago
    now = datetime.now()
    one_month_ago = now - timedelta(days=30)

    # Use a pool of workers to run the commands in parallel
    def run_command(command):
        try:
            url = command[-1].replace('"', "")

            # Find command in the list of failed commands
            for check in checked_urls:
                date = datetime.strptime(check["date"], "%Y-%m-%d")
                if check["url"] == url and date > one_month_ago:
                    logger.info(
                        f"Skipping command for {url} as it was already checked on {check['date']}."
                    )
                    return subprocess.run(f"echo 'Skipping url'", shell=True)

            logger.info(f"Running command for url {command[-1]}")
            for index, arg in enumerate(command):
                if arg.startswith("--output-directory"):
                    out_dir = os.path.abspath(arg)
            os.makedirs(out_dir, exist_ok=True)
            # Run the command
            logger.debug(f"Running command: {' '.join(command)}")
            result = subprocess.run(" ".join(command), shell=True)
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {e}")
            return e

    with Pool(THREADS) as pool:
        results = pool.map(run_command, commands)
        for result in results:
            url = (
                result.args.split(" ")[-1].replace('"', "")
                if isinstance(result, subprocess.CompletedProcess)
                else None
            )
            if result.returncode != 0:
                logger.error(f"Command failed with return code {result.returncode}")
                if url:
                    checked_urls.append({"date": now.strftime("%Y-%m-%d"), "url": url})
                else:
                    logger.error(
                        f"No URL found in the command: {result.args if hasattr(result, 'args') else 'N/A'}"
                    )
            else:
                logger.info("Command executed successfully.")

                # Check for the number of args and skip if not enough args
                if len(result.args.split(" ")) < 8:
                    logger.debug(
                        f"Command did not have enough arguments to determine output directory and filename: {result.args}"
                    )
                    continue

                # Find if the file was successfully downloaded
                out_dir = result.args.split(" ")[5]
                filename_prefix = result.args.split(" ")[7].replace(
                    "{filename-extension}", ""
                )

                # Check if the file exists
                file_exists = False
                for root, _, files in os.walk(out_dir):
                    for file in files:
                        if file.startswith(filename_prefix):
                            file_exists = True
                            break

                if file_exists:
                    logger.info(
                        f"File {filename_prefix} successfully downloaded in {out_dir}."
                    )
                    # If url was in checked_urls, remove it
                    checked_urls = [
                        check for check in checked_urls if check["url"] != url
                    ]
                else:
                    logger.error(
                        f"File {filename_prefix} was not downloaded successfully in {out_dir}."
                    )
                    if url:
                        checked_urls.append(
                            {"date": now.strftime("%Y-%m-%d"), "url": url}
                        )

    # Remove any duplicates from checked_urls keeping the last entry
    seen_urls = set()
    checked_urls = [
        check
        for check in reversed(checked_urls)
        if check["url"] not in seen_urls and not seen_urls.add(check["url"])
    ]

    # Write the checked URLs to a CSV file
    with open(checked_urls_file, "w", newline="", encoding="utf-8") as csvfile:
        logger.info(f"Writing {len(checked_urls)} checked URLs to {checked_urls_file}")
        fieldnames = ["date", "url"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for check in checked_urls:
            writer.writerow(check)

    print("All commands executed successfully.")
