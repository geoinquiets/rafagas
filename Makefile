SHELL := /bin/bash

export DOCKER_UID := $(shell id -u)
export DOCKER_GID := $(shell id -g)
export DOCKER_SOCKET_GID := $(shell stat -c '%g' /var/run/docker.sock 2>/dev/null)

.PHONY: serve index microlink update build download-websites crawl clean check-links check-last-job

serve:
	docker compose up

index:
	docker compose run --rm scripts pagefind --site _site

clean:
	docker compose run --rm jekyll sh -c "bundle install && bundle exec jekyll clean"

microlink:
	docker compose run --rm scripts uv run script/microlink.py

update:
	docker compose run --rm -e DEEPL_API_KEY -e POST_DATE scripts uv run script/update_rafaga.py

download-websites: build
	docker compose run --rm scripts uv run script/download-websites.py

crawl:
	docker compose run --rm scripts uv run script/crawling/__main__.py

build:
	@docker compose exec jekyll bundle exec jekyll build 2>/dev/null || \
		docker compose run --rm jekyll sh -c "bundle install && bundle exec jekyll build"
	docker compose run --rm scripts pagefind --site _site

check-last-job:
	gh run view --log $$(gh run list -L 1| head -n1 | grep -Eo '[0-9]{9}')| grep -oP '(?<=External link ).*(?= failed)'

check-links:
	docker compose run --rm scripts uv run script/check-links/__main__.py