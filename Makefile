SHELL := /bin/bash
PYTHON := ./env/bin/python

.PHONY: serve microlink build download-websites crawl clean

serve:
	docker compose up

clean:
	docker compose run --rm jekyll jekyll clean

microlink:
	uv run script/microlink.py 

update:
	$(PYTHON) script/update_rafaga.py 

download-websites: build
	uv run script/download-websites.py

crawl:
	uv run script/crawling/__main__.py

build:
	@docker compose exec jekyll jekyll build 2>/dev/null || \
		docker compose run --rm jekyll jekyll build

check-last-job:
	gh run view --log $$(gh run list -L 1| head -n1 | grep -Eo '[0-9]{9}')| grep -oP '(?<=External link ).*(?= failed)'

check-links:
	$(PYTHON) script/check-links/