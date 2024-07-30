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

from crawl_url import processLink, getHash

PROCESSED = "Processed"
SKIPPED = "Skipped"
IGNORED = "Ignored"
FAILED = "Failed"

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
logger.info(f"LOG_LEVEL={LOG_LEVEL}")
logger.info(f"LINKS_PROCESS={LINKS_PROCESS}")


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

    results = []

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
                    results.append(PROCESSED)
                except TypeError as e:
                    logger.critical(e.with_traceback())
                    logger.critical(f"Error processing {link} at {post['rid']}")
                    import sys
                    sys.exit(1)
        
        else:
            logger.debug("Link already processed")
            results.append(SKIPPED)
    return results


def processFile(md):
    with md.open() as md_reader:
        post = frontmatter.load(md_reader)
        if "rid" in post:
            rid = post["rid"]
            logger.debug("Processing rafaga {}...".format(rid))
            results = processRafaga(post)
            if results is None:
                logger.debug("Rafaga %s processing failed", rid)
                return { "rid": rid, "result": [FAILED]}
            else:
                return {"rid": rid, "result": results}
        else:
            logger.warning(f"Post without rid: {md}")
            return {"result": [IGNORED]}


if __name__ == "__main__":
    # Main
    p = Path(f"{os.path.dirname(__file__)}/../../_posts/")

    allPosts = list(filter(lambda f: str(f).find("template") == -1, p.glob("**/*.md")))
    logger.info("%s rafagas in the repository", len(allPosts))

    randomizedPosts = list(allPosts)
    random.shuffle(randomizedPosts)

    posts = randomizedPosts[:LINKS_PROCESS]

    with Pool(POOL_SIZE) as p:
        results = p.map(processFile, posts)


    read = ignored = skipped = failed = 0

    for item in results:
        for result in item["result"]: 
            if result == PROCESSED: read += 1
            elif result == SKIPPED: skipped += 1
            elif result == IGNORED: ignored += 1
            elif result == FAILED: failed += 1

    logger.info("=== Files processed ===")
    logger.info(f"Files processed: {len(posts)}")
    logger.info(f"Ignored: {ignored}")

    logger.info("=== Links processed ===")
    logger.info(f"Read: {read}")
    logger.info(f"Skipped: {skipped}")
    logger.info(f"Failed: {failed}")