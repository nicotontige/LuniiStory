# Local checks, mirroring what GitHub Actions runs.
#
#   make           everything that can be checked without pushing
#   make run       launch the app from the source tree
#   make build     package for this machine, then smoke-test the result
#   make run-dist  launch the packaged app
#   make rehearse  run the release build on all four platforms, publishing nothing

VENV    := .venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
VERSION := $(shell $(PYTHON) -c "import luniistory; print(luniistory.__version__)" 2>/dev/null)

.DEFAULT_GOAL := check
.PHONY: check run test lint i18n build smoke run-dist rehearse release clean venv

check: test lint i18n
	@echo "✓ ready to build"

venv: $(VENV)/bin/python

$(VENV)/bin/python:
	python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements-dev.txt

# What you want while developing: no packaging step, starts in a second.
# Arguments are passed through, so `make run ARGS="list --age 5"` works too.
run: venv
	$(PYTHON) -m luniistory $(ARGS)

test: venv
	$(PYTHON) -m pytest -q

lint: venv
	$(PYTHON) -m pyflakes luniistory tools tests
	@command -v actionlint >/dev/null && actionlint .github/workflows/*.yml \
		|| echo "  (actionlint absent, workflows not checked — brew install actionlint)"

i18n: venv
	$(PYTHON) tools/extract_strings.py

build: venv
	$(PIP) install --quiet -r requirements-dev.txt
	$(VENV)/bin/pyinstaller --noconfirm --log-level WARN luniistory.spec
	@$(MAKE) --no-print-directory smoke
	@echo "→ launch it with: make run-dist"

# The packaged binary is what users actually run, so exercise it rather than
# trusting that the build merely finished. Each line covers a resource that a
# packaging change can silently drop.
smoke:
	@echo "→ smoke-testing the packaged build"
	@if [ -d dist/luniiStory.app ]; then \
		BIN=dist/luniiStory.app/Contents/MacOS/luniistory; \
	else \
		BIN=dist/luniistory/luniistory; \
	fi; \
	"$$BIN" lang | grep -q "fr" || { echo "  ✗ translation catalogs missing"; exit 1; }; \
	echo "  translations bundled"; \
	"$$BIN" --lang en cache >/dev/null || { echo "  ✗ cannot reach its own config"; exit 1; }; \
	echo "  library reachable"; \
	"$$BIN" devices >/dev/null 2>&1; \
	test $$? -le 1 || { echo "  ✗ Lunii engine failed to load"; exit 1; }; \
	echo "  Lunii engine loads"; \
	echo "  version $(VERSION)"

run-dist:
	@if [ -d dist/luniiStory.app ]; then \
		open dist/luniiStory.app; \
	else \
		dist/luniistory/luniistory; \
	fi

rehearse:
	gh workflow run release.yml --ref $$(git branch --show-current)
	@echo "→ watch it with: gh run watch \$$(gh run list --workflow=release.yml --limit 1 --json databaseId --jq '.[0].databaseId')"

# Refuses to tag a dirty tree or a version that is already released.
release: check
	@test -z "$$(git status --porcelain)" || { echo "✗ uncommitted changes"; exit 1; }
	@git rev-parse "v$(VERSION)" >/dev/null 2>&1 && { echo "✗ v$(VERSION) already tagged"; exit 1; } || true
	@echo "→ tagging v$(VERSION)"
	git tag -a "v$(VERSION)" -m "luniiStory $(VERSION)"
	@echo "→ push it when ready: git push origin v$(VERSION)"

clean:
	rm -rf build dist *.spec.bak
	find . -name __pycache__ -prune -exec rm -rf {} +
