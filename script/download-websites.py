#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import csv
from dataclasses import dataclass
from multiprocessing import Pool
import os
import shutil
import subprocess
from datetime import datetime, timedelta

DEFAULT_DOCKER_IMAGE = "capsulecode/singlefile"
DEFAULT_CSV_FILE = "_site/archive.csv"
DEFAULT_OUT_DIR = "crawl_sites"
DEFAULT_THREADS = 6
DEFAULT_SUBSET = 0
DEFAULT_BROWSER_WAIT_DELAY = "40000"  # 40 seconds


@dataclass
class DownloadTask:
    """Holds a download command together with its metadata."""
    command: list
    url: str
    out_dir: str
    filename_prefix: str

# set up logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def process_links(csv_file, out_dir, docker_image, subset):
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

            #random.seed(42)  # For reproducibility
            random.shuffle(rows)
            if subset > len(rows):
                print(
                    f"Subset size {subset} is larger than the number of commands {len(rows)}. Adjusting to {len(rows)}."
                )
                subset = len(rows)
            rows = rows[:subset]

        tasks = []
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
            abs_out_date_dir = os.path.abspath(out_date_dir)
            file_exists = False

            # walk the directory tree to find the file
            for root, _, files in os.walk(out_date_dir):
                for file in files:
                    if file.startswith(basename):
                        file_exists = True
                        break
            if file_exists:
                logger.debug(
                    f"File {basename} already exists at {out_date_dir}, skipping download."
                )
            else:
                logger.debug(
                    f"File {basename} does not exist, it will be downloaded at {out_date_dir}"
                )

                filename_prefix = f"{basename}."

                # Build docker command with volume mount for the output directory
                tasks.append(
                    DownloadTask(
                        command=[
                            "docker", "run", "--rm",
                            "-v", f"{abs_out_date_dir}:/usr/src/app/out",
                            docker_image,
                            "--dump-content=false",
                            "--browser-wait-delay", DEFAULT_BROWSER_WAIT_DELAY,
                            "--filename-template", f"{filename_prefix}{{filename-extension}}",
                            url,
                        ],
                        url=url,
                        out_dir=abs_out_date_dir,
                        filename_prefix=filename_prefix,
                    )
                )

        return tasks


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
        "--docker-image",
        help="Docker image for single-file-cli.",
        default=DEFAULT_DOCKER_IMAGE,
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
    DOCKER_IMAGE = args.docker_image
    SUBSET = args.subset

    if not shutil.which("docker"):
        logger.error(
            "docker not found on PATH. "
            "Install Docker: https://docs.docker.com/get-docker/"
        )
        raise SystemExit(1)

    # Ensure the Docker image is available locally
    result = subprocess.run(
        ["docker", "image", "inspect", DOCKER_IMAGE],
        capture_output=True,
    )
    if result.returncode != 0:
        logger.info(f"Docker image '{DOCKER_IMAGE}' not found locally, pulling...")
        pull = subprocess.run(["docker", "pull", DOCKER_IMAGE])
        if pull.returncode != 0:
            logger.error(f"Failed to pull Docker image '{DOCKER_IMAGE}'.")
            raise SystemExit(1)

    tasks = process_links(CSV_FILE, OUT_DIR, DOCKER_IMAGE, SUBSET)

    logger.info(f"{len(tasks)} tasks to run in {THREADS} processes.")

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

    # Use a pool of workers to run the tasks in parallel
    def run_task(task):
        try:
            # Check if this URL was already checked recently
            for check in checked_urls:
                date = datetime.strptime(check["date"], "%Y-%m-%d")
                if check["url"] == task.url and date > one_month_ago:
                    logger.info(
                        f"Skipping {task.url} as it was already checked on {check['date']}."
                    )
                    return task, None  # None signals a skip

            logger.info(f"Running command for url {task.url}")
            os.makedirs(task.out_dir, exist_ok=True)
            logger.debug(f"Running command: {task.command}")
            result = subprocess.run(task.command)
            return task, result
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return task, e

    with Pool(THREADS) as pool:
        outcomes = pool.map(run_task, tasks)
        for task, result in outcomes:
            # Skipped tasks
            if result is None:
                continue

            # Failed tasks
            if not isinstance(result, subprocess.CompletedProcess) or result.returncode != 0:
                rc = result.returncode if hasattr(result, "returncode") else "N/A"
                logger.error(f"Command failed (rc={rc}) for {task.url}")
                checked_urls.append({"date": now.strftime("%Y-%m-%d"), "url": task.url})
                continue

            # Successful tasks — verify the file was actually created
            logger.info("Command executed successfully.")
            file_exists = False
            for root, _, files in os.walk(task.out_dir):
                for file in files:
                    if file.startswith(task.filename_prefix):
                        file_exists = True
                        break

            if file_exists:
                logger.info(
                    f"File {task.filename_prefix}* successfully downloaded in {task.out_dir}."
                )
                # Remove from checked_urls if previously failed
                checked_urls = [
                    check for check in checked_urls if check["url"] != task.url
                ]
            else:
                logger.error(
                    f"File {task.filename_prefix}* was not downloaded in {task.out_dir}."
                )
                checked_urls.append(
                    {"date": now.strftime("%Y-%m-%d"), "url": task.url}
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
