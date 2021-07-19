#!/usr/bin/env python
# coding: utf-8

# In[1]:

import re
import sys
import math
import random
import logging
from multiprocessing import Pool
from pathlib import Path
import requests
from requests import Timeout
import urllib3
import datetime
import frontmatter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'
try:
    requests.packages.urllib3.contrib.pyopenssl.util.ssl_.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'
except AttributeError:
    # no pyopenssl support used / needed / available
    pass


# create logger
for key in logging.Logger.manager.loggerDict:
    logging.getLogger(key).setLevel(logging.CRITICAL)
    
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

LOG_LEVEL = logging.INFO
LOG_FORMAT = ' %(asctime)s - %(levelname)-8s %(message)s'
LOG_DATE_FMT = '%I:%M:%S %p'

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FMT)

logger = logging.getLogger('check_url')
logger.setLevel(LOG_LEVEL)
logger.info('Logger set up')


# In[2]:


# Constants
HEADERS = {
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.106 Safari/537.36',
    'Accept': 'text/html',
    'Accept-Language': 'es-ES,es;q=0.9,ca;q=0.8,en-US;q=0.7,en;q=0.6'
}
TIMEOUT = 2;
MAX_TIMEOUT = 17;
POOL_SIZE = 15;
CHECK_DAYS = 7;


# In[3]:


# Functions
def replaceHttpHttps(url):
    return re.sub('^http:', 'https:', url)
    

def checkUrl(url, timeout=TIMEOUT):
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
    
def filterInvalid(rafaga):
    link = rafaga['link']
    if 'invalid' in rafaga and (rafaga['invalid'] == True or rafaga['invalid'] == 'true'):
        logger.debug(f'[Invalid] Skipping {link}')
        return False
    return True

def processRafaga(post, skipInvalids = True):
    rafagas = filter(filterInvalid, post['rafagas']) if skipInvalids else post['rafagas']
    
    for rafaga in rafagas:
        link = rafaga['link']
        now = datetime.datetime.now()
        lastCheck = datetime.datetime.fromisoformat(rafaga['lastCheck']) if 'lastCheck' in rafaga else now 
                
        if lastCheck == now or (now - lastCheck).days > CHECK_DAYS:
            logger.debug(f"Checking {link}")
            linkCheck = checkUrl(link)
            rafaga['lastCheck'] = lastCheck.isoformat()
            
            if linkCheck['code'] >= 400:
                rafaga['invalid'] = True
            if linkCheck['url'] != link:
                rafaga['link'] = linkCheck['url']
        else:
            logger.debug(f'[Checked] Skipping {link}')
    return post

def processFile(md):
    result = 'Not a rafaga'
    with md.open() as md_reader:
        post = frontmatter.load(md_reader)
        if ('rid' in post):
            rid = post['rid']
            result = 'Read'
            logger.debug('Processing rafaga {}...'.format(rid))
            post_processed = processRafaga(post)
            if post_processed is not None:
                result = 'Written'
                with md.open(mode='w') as md_writer:
                    md_writer.write(frontmatter.dumps(post_processed))
                logger.debug('Rafaga %s processed with result %s', rid, result)
        return {
            'file': str(md),
            'result': result
        }


# In[ ]:


# Main
p = Path('../_posts/')


if len(sys.argv) != 2:
    raise ValueError('Please provide a number of Rafagas to process')
else:
    postsToProcess = int(sys.argv[1])

allPosts = list(filter(lambda f: str(f).find('template') == -1, p.glob('**/*.md')))
logger.info('%s rafagas in the repository', len(allPosts))

randomizedPosts = list(allPosts)
random.shuffle(randomizedPosts)

posts = randomizedPosts[:postsToProcess]

logger.info('Processing %s rafagas',postsToProcess)

with Pool(POOL_SIZE) as p:
    results = p.map(processFile, posts)

logger.info(f'{len(posts)} rafagas processed')


# In[6]:
# checkUrl('http://opensolarmap.com')

