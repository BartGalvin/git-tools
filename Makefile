SHELL_SCRIPTS := gbinit gitorigin.sh

.PHONY: check lint test

check: lint test

lint:
	@for script_file in $(SHELL_SCRIPTS); do bash -n "$$script_file" || exit; done
	shellcheck $(SHELL_SCRIPTS)

test:
	python3 -B -m unittest discover -s tests -v
