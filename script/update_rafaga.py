import logging
from pathlib import Path
import frontmatter
import re

for key in logging.Logger.manager.loggerDict:
    logging.getLogger(key).setLevel(logging.CRITICAL)


def process(post):
    # Simple keys
    post['layout'] = 'rafaga'
    del(post['tags'])
    
    # Title
    title_match = re.search('^Nº(?:\ )?([0-9]{1,4}):(?:\ )?(.*)$',post['title'])
    if title_match:
        rid = title_match.group(1)
        post['rid'] = rid
        
        keywords = list(map(lambda x: x.strip(),title_match.group(2).split(',')))
        del(post['title'])
    else:
        raise Exception('\n#####\nNo match\n#####')
    
    # Content
    content = post.content
    items = filter(lambda x: x!='', content.split('\n*'))
    post.content = ''
    
    rafagas = []
    
    for item in items:
        item_split = re.split('\n',item)
        desc_via = re.split(' via @',item_split[0].strip('.#!* '))
        
        rafaga = {
            'link': item_split[1].strip(),
            'desc': desc_via[0],
            'keyw': keywords.pop(0)
        }
        
        if len(desc_via)>1:
            rafaga['via'] = '@' + desc_via[1]
        
        rafagas.append(rafaga)
    post['rafagas'] = rafagas
    
    return post


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=' %(asctime)s - %(levelname)-8s %(message)s',
        datefmt='%I:%M:%S %p')

    p = Path('_posts/')
    for md in sorted(p.glob('**/*.md'), reverse=True):
        with md.open() as md_reader:
            post = frontmatter.load(md_reader)
            if (post['layout'] == 'post'):
                try:
                    logging.info('Processing rafaga {}...'.format(post['date']))
                    post_processed = process(post)
                    if post_processed is not None:
                        with md.open(mode='w') as md_writer:
                            md_writer.write(frontmatter.dumps(post_processed))
                except Exception as err:
                    print(err)
