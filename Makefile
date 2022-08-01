SHELL := /bin/bash
BUNDLE := bundle
JEKYLL := $(BUNDLE) exec jekyll
PYTHON := ./env/bin/python

.PHONY: serve microlink build

serve:
	JEKYLL_ENV=production RUBYOPT='-W0' $(JEKYLL) serve  --incremental --port 8000 --future

clean:
	RUBYOPT='-W0' $(JEKYLL) clean

microlink:
	$(PYTHON) script/microlink.py 

update:
	$(PYTHON) script/update_rafaga.py 

build:
	RUBYOPT='-W0' $(JEKYLL) build

check-last-job:
	gh run view --log $$(gh run list -L 1| head -n1 | grep -Eo '[0-9]{9}')| grep -oP '(?<=External link ).*(?= failed)'