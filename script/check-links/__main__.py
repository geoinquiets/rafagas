#!/usr/bin/env python
import os
import sys
import random
import logging
from multiprocessing import Pool
from pathlib import Path
import datetime
import frontmatter

from check_url import checkUrl


# create logger
for key in logging.Logger.manager.loggerDict:
    logging.getLogger(key).setLevel(logging.CRITICAL)

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

LINKS_PROCESS = int(os.environ.get("LINKS_PROCESS") or 50)
LINKS_CHECK_INVALIDS = os.environ.get("LINKS_CHECK_INVALIDS","Y") == "Y"

LOG_LEVEL = os.environ.get("LINKS_LOG_LEVEL") or logging.INFO
LOG_FORMAT = " %(asctime)s - %(levelname)-8s %(message)s"
LOG_DATE_FMT = "%I:%M:%S %p"

POOL_SIZE = 15
LINKS_DAYS = int(os.environ.get("CHECK_DAYS") or 7)

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FMT)

logger = logging.getLogger("fix_links")
logger.setLevel(LOG_LEVEL)

logger.info("Logger set up")
logger.info(f"LOG_LEVEL={LOG_LEVEL}")
logger.info(f"LINKS_PROCESS={LINKS_PROCESS}")
logger.info(f"LINKS_CHECK_INVALIDS={LINKS_CHECK_INVALIDS}")
logger.info(f"LINKS_DAYS={LINKS_DAYS}")


# Functions


def filterInvalid(rafaga):
    link = rafaga["link"]
    if "invalid" in rafaga and (
        rafaga["invalid"] == True or rafaga["invalid"] == "true"
    ):
        logger.debug(f"[Invalid] Skipping {link}")
        return False
    return True


def processRafaga(post, skipInvalids=True):
    rafagas = list(
        filter(filterInvalid, post["rafagas"]) if skipInvalids else post["rafagas"]
    )
    logger.debug(f"{len(rafagas)} links in this rafaga to process")

    for rafaga in rafagas:
        link = rafaga["link"]
        now = datetime.datetime.now()
        lastCheck = (
            datetime.datetime.fromisoformat(rafaga["lastCheck"])
            if "lastCheck" in rafaga
            else None
        )

        if lastCheck == None or (now - lastCheck).days > LINKS_DAYS:
            logger.debug(f"Checking {link}")
            linkCheck = checkUrl(link)
            
            # Reset the invalid key
            rafaga.pop("invalid", None)
            if linkCheck["code"] >= 400:
                rafaga["invalid"] = True
            # Reset the url if got a new one
            elif linkCheck["url"] != link:
                rafaga["link"] = linkCheck["url"]
            
            # Set the new check date
            rafaga["lastCheck"] = now.isoformat()
        else:
            logger.debug(f"[Checked] Skipping in rafaga {post['rid']}: {link}")

    return post


def processFile(md):
    result = "Not a rafaga"
    with md.open() as md_reader:
        post = frontmatter.load(md_reader)
        if "rid" in post:
            rid = post["rid"]
            result = "Read"
            logger.debug("Processing rafaga {}...".format(rid))
            post_processed = processRafaga(post, skipInvalids=(not LINKS_CHECK_INVALIDS))
            if post_processed is not None:
                result = "Written"
                with md.open(mode="w") as md_writer:
                    md_writer.write(frontmatter.dumps(post_processed))
                logger.debug("Rafaga %s processed with result %s", rid, result)
        return {"file": str(md), "result": result}


if __name__ == "__main__":
    # Main
    p = Path(f"{os.path.dirname(__file__)}/../../_posts/")

    allPosts = list(filter(lambda f: str(f).find("template") == -1, p.glob("**/*.md")))
    logger.info("%s rafagas in the repository", len(allPosts))

    randomizedPosts = list(allPosts)
    random.shuffle(randomizedPosts)

    posts = randomizedPosts[:LINKS_PROCESS]

    logger.info("Processing %s rafagas", LINKS_PROCESS)

    with Pool(POOL_SIZE) as p:
        results = p.map(processFile, posts)

    logger.info(f"{len(posts)} rafagas processed")