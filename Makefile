SHELL := /bin/bash
BUNDLE := bundle
JEKYLL := $(BUNDLE) exec jekyll
PYTHON := ./env/bin/python

.PHONY: serve microlink build

serve:
	JEKYLL_ENV=production RUBYOPT='-W0' $(JEKYLL) serve  --incremental --port 8000

clean:
	RUBYOPT='-W0' $(JEKYLL) clean

microlink:
	$(PYTHON) script/microlink.py 

build:
	RUBYOPT='-W0' $(JEKYLL) build

check-last-job:
	gh run view --log $$(gh run list | head -n1 | grep -Eo '[0-9]+$$')| grep -oP '(?<=External link ).*(?= failed)'