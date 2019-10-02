SHELL := /bin/bash
BUNDLE := bundle
JEKYLL := $(BUNDLE) exec jekyll
PYTHON := ./env/bin/python

PROJECT_DEPS := Gemfile package.json

.PHONY: serve microlink build

serve:
	JEKYLL_ENV=production $(JEKYLL) serve  --incremental --port 8000

clean:
	$(JEKYLL) clean

microlink:
	$(PYTHON) script/microlink.py 

build:
	$(JEKYLL) build

