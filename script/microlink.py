import requests
import logging
from pathlib import Path
import frontmatter
import time

for key in logging.Logger.manager.loggerDict:
    logging.getLogger(key).setLevel(logging.CRITICAL)


class Microlink(object):
    MICROLINK_API = "https://api.microlink.io"
    HAS_REACHED_LIMIT = False

    microlink_counter = 0

    @staticmethod
    def microlink(url):
        try:
            r = requests.get(url=Microlink.MICROLINK_API, params={'url': url})
            Microlink.microlink_counter += 1

            r_json = r.json()
            if 'status' in r_json and r_json['status'] == 'success':
                data = r_json['data']

                result = {}

                title = data['title']
                desc = data['description']
                image = data['image']['url'] if data.get(
                    'image') and type(data.get('image')) is dict else None
                logo = data['logo']['url'] if data.get(
                    'logo') and type(data.get('logo')) is dict else None

                if image:
                    result['image'] = image
                if desc:
                    result['desc'] = desc
                if title:
                    result['title'] = title
                if logo:
                    result['logo'] = logo
                return result
            elif r_json['status'] == 'fail':
                message = r_json['message']
                logging.error('Microlink error: {}'.format(message))
                if r.status_code == 429:
                    Microlink.HAS_REACHED_LIMIT = True
                return None

        except Exception as e:
            logging.error('Error processing {}'.format(url))
            logging.error(e)


def process(post):
    for rafaga in post['rafagas']:
        logging.debug(rafaga['link'])
        if rafaga.get('microlink') is not None or rafaga.get('invalid') or rafaga.get('nocheck'):
            logging.debug('Skipping link')
        elif Microlink.HAS_REACHED_LIMIT is not True:
            microlink_data = Microlink.microlink(rafaga['link'])
            if microlink_data is not None:
                rafaga['microlink'] = microlink_data
                time.sleep(2)

    return post


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=' %(asctime)s - %(levelname)-8s %(message)s',
        datefmt='%I:%M:%S %p')

    p = Path('_posts/')
    for md in sorted(p.glob('2020/*.md'), reverse=True)[:5]:
            
        if Microlink.HAS_REACHED_LIMIT:
            logging.warning('At Microlink limit, aborting')
            break
        if str(md).find('template') == -1 :
            with md.open() as md_reader:
                post = frontmatter.load(md_reader)
                if ('rid' in post):
                    rid = post['rid']
                    logging.info('Processing rafaga {}...'.format(rid))
                    post_processed = process(post)
                    if post_processed is not None:
                        with md.open(mode='w') as md_writer:
                            md_writer.write(frontmatter.dumps(post_processed))

    logging.info('Made {} requests to microlink'.format(Microlink.microlink_counter))
