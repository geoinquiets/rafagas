import requests
import requests
import math
import re
from requests import Timeout
import urllib3
import logging
import os
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Constants
LOG_LEVEL = os.environ.get('LINKS_LOG_LEVEL') or logging.INFO
LOG_FORMAT = ' %(asctime)s - %(levelname)-8s %(message)s'
LOG_DATE_FMT = '%I:%M:%S %p'


MAX_TIMEOUT = 17;
TIMEOUT = 2;

HEADERS = {
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.106 Safari/537.36',
    'Accept': 'text/html',
    'Accept-Language': 'es-ES,es;q=0.9,ca;q=0.8,en-US;q=0.7,en;q=0.6'
}
logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FMT)

logger = logging.getLogger('check_url')
logger.setLevel(LOG_LEVEL)

def replaceHttpHttps(url):
    return re.sub('^http:', 'https:', url)

def checkUrl(url, timeout=TIMEOUT):
    logger.info(url)
    try:
        rHead = requests.head(
            url,
            headers = HEADERS,
            allow_redirects = False,
            timeout = timeout,
            verify = False
        )
        
        urlR = rHead.headers['Location'] if 'Location' in rHead.headers and rHead.headers['Location'][:4] == 'http' else url

        rGet = requests.get(
            urlR,
            headers= HEADERS,
            timeout = timeout,
            verify=False
        )
        
        code = 200 if rGet.status_code == 403 and 'Server' in rGet.headers and rGet.headers['Server'].lower() == 'cloudflare' else rGet.status_code
        
        return {
            'url': urlR,
            'code': code
        }
    except Timeout as e:
        if re.match('^http:', url):
            logger.debug(f'trying {url} with https')
            return checkUrl(replaceHttpHttps(url))
        else:
            if timeout < MAX_TIMEOUT:
                new_timeout = math.floor(timeout * 2.0)
                logger.debug(f'trying {url} increasing the timeout to {new_timeout}')
                return checkUrl(url, timeout= new_timeout)
            else:
                return {
                    'url': url,
                    'code': 504
                }
    except Exception as e:
        logger.error(e)
        return {
            'url': url,
            'code': 500
        }


if __name__ == "__main__":
    try:
        url = sys.argv[1]
        check = checkUrl(url, TIMEOUT)
        logger.info(check)
    except Exception as e:
        logger.error(e)