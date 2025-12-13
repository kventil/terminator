PYTHON ?= python3

.PHONY: help install run dates confirm

help:
	@echo "Targets: install, run, dates, confirm"

install:
	$(PYTHON) -m pip install -e .

run:
	$(PYTHON) -m termin_ator.cli --help

dates:
	termin-ator dates --portal S55299BD3

confirm:
	termin-ator confirm 123456 --portal S55299BD3

