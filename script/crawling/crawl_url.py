import logging
import frontmatter
import os
import sys
import hashlib
import dateutil.parser
from trafilatura import fetch_url, extract_metadata, extract


# Constants
LOG_LEVEL = os.environ.get('LINKS_LOG_LEVEL') or logging.DEBUG
LOG_FORMAT = ' %(asctime)s - %(levelname)-8s %(message)s'
LOG_DATE_FMT = '%I:%M:%S %p'

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FMT)

logger = logging.getLogger('crawl')
logger.setLevel(LOG_LEVEL)

def getHash(link):
     md5 = hashlib.md5(link.encode('utf-8'))
     return md5.hexdigest()

def processLink(postId, postDate, rafagaData):
    link = rafagaData["link"]
    postDateProcssed = postDate
    if type(postDate) is str:
        try:
            logger.debug(f"Processing {postDate}")
            postDateProcssed =  dateutil.parser.isoparse(postDate).isoformat()
        except ValueError as e:
            logger.critical(postDate)
            logger.critical(e)
            postDateProcssed = postDate
    else:
        try:
            postDateProcssed = postDate.isoformat()
        except ValueError as e:
            logger.critical(postDate)
            logger.critical(e)
            postDateProcssed = postDate
    # Get the basic data from the rafaga
    data = {
        "id": getHash(rafagaData["link"]),
        "date": postDateProcssed,
        "digestId": postId,
        "keyword": rafagaData["keyw"],
        "link": link
    }

    # If present, insert the cached metadata
    if "microlink" in rafagaData:
         data["metadata"] = dict(rafagaData["microlink"])

    # Crawl the site
    downloaded = fetch_url(link)
    if downloaded:
        data['crawl'] = {
             'content': downloaded
        }
        # Get metadata
        metadata = extract_metadata(downloaded, default_url=link)
        if metadata:
            data['crawl'].update({k: v for k, v in metadata.as_dict().items() if v})
        # Extract text
        text = extract(downloaded, url=link, include_links=True, favor_precision=True)
        if text: 
             data['crawl'].update({ "text": text})
    else:
         logger.warn(f"Can't crawl: {link}")
    return data


if __name__ == "__main__":

        file = sys.argv[1]
        with open(file) as reader:
            post = frontmatter.load(reader)
            processLink(post["rid"], post["date"], post["rafagas"][0])
