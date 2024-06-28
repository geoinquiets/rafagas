#!/usr/bin/env python
import os
import re
import random
import logging
from multiprocessing import Pool
from pathlib import Path
import datetime
import frontmatter

from utils.check_url import checkUrl


# create logger
for key in logging.Logger.manager.loggerDict:
    logging.getLogger(key).setLevel(logging.CRITICAL)

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

LINKS_PROCESS = int(os.environ.get("LINKS_PROCESS") or 50)
LOG_LEVEL = os.environ.get("LINKS_LOG_LEVEL") or logging.INFO
LOG_FORMAT = " %(asctime)s - %(levelname)-8s %(message)s"
LOG_DATE_FMT = "%I:%M:%S %p"

POOL_SIZE = 15
CHECK_DAYS = 7

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FMT)

logger = logging.getLogger("fix_links")
logger.setLevel(LOG_LEVEL)
logger.info("Logger set up")


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
    rafagas = (
        filter(filterInvalid, post["rafagas"]) if skipInvalids else post["rafagas"]
    )

    for rafaga in rafagas:
        link = rafaga["link"]
        now = datetime.datetime.now()
        lastCheck = (
            datetime.datetime.fromisoformat(rafaga["lastCheck"])
            if "lastCheck" in rafaga
            else now
        )

        if lastCheck == now or (now - lastCheck).days > CHECK_DAYS:
            logger.debug(f"Checking {link}")
            linkCheck = checkUrl(link)
            rafaga["lastCheck"] = lastCheck.isoformat()

            if linkCheck["code"] >= 400:
                rafaga["invalid"] = True
            if linkCheck["url"] != link:
                rafaga["link"] = linkCheck["url"]
        else:
            logger.info(f"[Checked] Skipping in rafaga {post['rid']}: {link}")
    return post


def processFile(md):
    result = "Not a rafaga"
    with md.open() as md_reader:
        post = frontmatter.load(md_reader)
        if "rid" in post:
            rid = post["rid"]
            result = "Read"
            logger.debug("Processing rafaga {}...".format(rid))
            post_processed = processRafaga(post)
            if post_processed is not None:
                result = "Written"
                with md.open(mode="w") as md_writer:
                    md_writer.write(frontmatter.dumps(post_processed))
                logger.info("Rafaga %s processed with result %s", rid, result)
        return {"file": str(md), "result": result}





if __name__ == "__main__":
    # Main
    p = Path(f"{os.path.dirname(__file__)}/../_posts/")

    allPosts = list(filter(lambda f: str(f).find("template") == -1, p.glob("**/*.md")))
    logger.info("%s rafagas in the repository", len(allPosts))

    randomizedPosts = list(allPosts)
    random.shuffle(randomizedPosts)

    posts = randomizedPosts[:LINKS_PROCESS]

    logger.info("Processing %s rafagas", LINKS_PROCESS)

    with Pool(POOL_SIZE) as p:
        results = p.map(processFile, posts)

    logger.info(f"{len(posts)} rafagas processed")