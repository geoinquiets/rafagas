SHELL := /bin/bash

.PHONY: serve microlink build download-websites crawl clean check-links check-last-job

serve:
	docker compose up

clean:
	docker compose run --rm jekyll jekyll clean

microlink:
	docker compose run --rm scripts uv run script/microlink.py

download-websites: build
	docker compose run --rm scripts uv run script/download-websites.py

crawl:
	docker compose run --rm scripts uv run script/crawling/__main__.py

build:
	@docker compose exec jekyll jekyll build 2>/dev/null || \
		docker compose run --rm jekyll jekyll build

check-last-job:
	gh run view --log $$(gh run list -L 1| head -n1 | grep -Eo '[0-9]{9}')| grep -oP '(?<=External link ).*(?= failed)'

check-links:
	docker compose run --rm scripts uv run script/check-links/__main__.py