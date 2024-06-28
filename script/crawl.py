#!/usr/bin/env python
import os
import os.path
import random
import logging
from multiprocessing import Pool
from pathlib import Path
import frontmatter
import json
from pathlib import Path

from utils.crawl_url import processLink, getHash


# create logger
for key in logging.Logger.manager.loggerDict:
    logging.getLogger(key).setLevel(logging.CRITICAL)

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

LINKS_PROCESS = int(os.environ.get("LINKS_PROCESS") or 50)
LOG_LEVEL = os.environ.get("LINKS_LOG_LEVEL") or logging.INFO
LOG_FORMAT = " %(asctime)s - %(levelname)-8s %(message)s"
LOG_DATE_FMT = "%I:%M:%S %p"

POOL_SIZE = 18

DESTINATION_DIR = "./crawl"

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
    rafagaFolder = f"{DESTINATION_DIR}/{post['rid']}"
    Path(rafagaFolder).mkdir(parents=True, exist_ok=True)

    rafagas = (
        filter(filterInvalid, post["rafagas"]) if skipInvalids else post["rafagas"]
    )

    for rafaga in rafagas:
        link = rafaga["link"]
        hash = getHash(link)
        if not os.path.isfile(f"{rafagaFolder}/{hash}.json"):
            logger.debug(f"Checking {link}")
            try:
                data = processLink(post["rid"], post["date"], rafaga)
            except TypeError as e:
                logger.critical(e.with_traceback())
                logger.critical(f"Error processing link {link} at  {post['rid']}")
                import sys
                sys.exit(1)

            if data:
                try:
                    with open(f"{rafagaFolder}/{data['id']}.json", "w") as writer:
                        writer.write(json.dumps(data))
                except TypeError as e:
                    logger.critical(e.with_traceback())
                    logger.critical(f"Error processing {link} at {post['rid']}")
                    import sys
                    sys.exit(1)
        
        else:
            logger.debug("Link already processed")


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
                result = "Failed"
                logger.debug("Rafaga %s processed with result %s", rid, result)
        return {"rid": rid, "result": result}


if __name__ == "__main__":
    # Main
    p = Path(f"{os.path.dirname(__file__)}/../_posts/")

    allPosts = list(filter(lambda f: str(f).find("template") == -1, p.glob("**/*.md")))
    logger.info("%s rafagas in the repository", len(allPosts))

    # randomizedPosts = list(allPosts)
    # random.shuffle(randomizedPosts)

    posts = allPosts[:LINKS_PROCESS]

    logger.info("Processing %s rafagas", LINKS_PROCESS)

    with Pool(POOL_SIZE) as p:
        results = p.map(processFile, posts)

    logger.info(f"{len(posts)} rafagas processed")
