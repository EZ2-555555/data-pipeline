# ---------------------------------------------------------------------------
# SAM Makefile build — thin function packages
# ---------------------------------------------------------------------------
#
# Embeddings use the HuggingFace Inference API on Lambda (no torch needed).
# Each function packages lightweight deps + src/ only.
#
# Build graph:  build-*Function → install-light-deps → cp + src/
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Function packages — lightweight deps + src/
# ---------------------------------------------------------------------------
LIGHT_DEPS := $(CURDIR)/.lambda-light-deps

.PHONY: install-light-deps
install-light-deps:
	@if [ ! -f "$(LIGHT_DEPS)/.installed" ]; then \
		echo "Installing lightweight Lambda dependencies..."; \
		mkdir -p $(LIGHT_DEPS); \
		pip install -r requirements-lambda.txt -t $(LIGHT_DEPS)/; \
		touch $(LIGHT_DEPS)/.installed; \
	else \
		echo "Lightweight dependencies already cached, skipping install."; \
	fi

build-IngestionFunction: install-light-deps
	cp -r $(LIGHT_DEPS)/* $(ARTIFACTS_DIR)/ 2>/dev/null || true
	cp -r src $(ARTIFACTS_DIR)/src

build-PreprocessFunction: install-light-deps
	cp -r $(LIGHT_DEPS)/* $(ARTIFACTS_DIR)/ 2>/dev/null || true
	cp -r src $(ARTIFACTS_DIR)/src

build-RagApiFunction: install-light-deps
	cp -r $(LIGHT_DEPS)/* $(ARTIFACTS_DIR)/ 2>/dev/null || true
	cp -r src $(ARTIFACTS_DIR)/src

build-HealthCheckFunction: install-light-deps
	cp -r $(LIGHT_DEPS)/* $(ARTIFACTS_DIR)/ 2>/dev/null || true
	cp -r src $(ARTIFACTS_DIR)/src

# ---------------------------------------------------------------------------
# Validate samconfig-freetier.toml has no unfilled placeholders
# Run before deploying: make validate-config
# ---------------------------------------------------------------------------
validate-config:
	@echo "Checking samconfig-freetier.toml for unfilled placeholders..."
	@ERRORS=0; \
	grep -n "CHANGE_ME" infra/samconfig-freetier.toml && { echo "  ^^^ Replace CHANGE_ME with a real DB password"; ERRORS=1; } || true; \
	grep -n "hf_REPLACE_WITH_YOUR_TOKEN" infra/samconfig-freetier.toml && { echo "  ^^^ Replace hf_REPLACE_WITH_YOUR_TOKEN with your HuggingFace token from https://huggingface.co/settings/tokens"; ERRORS=1; } || true; \
	grep -n "xxxxxxxxxxxxxxxxx" infra/samconfig-freetier.toml && { echo "  ^^^ Replace placeholder VPC/subnet IDs with real ones from your AWS VPC console"; ERRORS=1; } || true; \
	if [ $$ERRORS -eq 0 ]; then echo "All placeholders filled — ready to deploy."; else echo "Fix the above before deploying."; exit 1; fi

# ---------------------------------------------------------------------------
# Sync local Docker data to AWS
#
# Two target environments:
#   Free Tier  — uses .env.freetier   (permanent IAM credentials, no rotation)
#   Learner Lab — uses .env.learnerlab (rotate credentials every ~4 hours)
#
# Setup:
#   cp .env.freetier.example .env.freetier   && fill in values
#   cp .env.learnerlab.example .env.learnerlab && fill in values
# ---------------------------------------------------------------------------

# helper: load a .env file and export its variables
define load_env
	$(eval ENV_FILE := $(1)) \
	$(eval include $(ENV_FILE)) \
	$(eval export $(shell sed 's/=.*//' $(ENV_FILE)))
endef

## Sync to Free Tier (S3 + RDS)
sync-freetier:
	@test -f .env.freetier || { echo "Missing .env.freetier — copy from .env.freetier.example and fill in values"; exit 1; }
	@echo "=== Syncing to Free Tier ==="
	env $$(grep -v '^#' .env.freetier | xargs) python -m src.sync_to_aws

sync-freetier-dry:
	@test -f .env.freetier || { echo "Missing .env.freetier — copy from .env.freetier.example and fill in values"; exit 1; }
	env $$(grep -v '^#' .env.freetier | xargs) python -m src.sync_to_aws --dry-run

## Sync to Learner Lab (S3 + RDS)
sync-learnerlab:
	@test -f .env.learnerlab || { echo "Missing .env.learnerlab — copy from .env.learnerlab.example and fill in values"; exit 1; }
	@echo "=== Syncing to Learner Lab ==="
	env $$(grep -v '^#' .env.learnerlab | xargs) python -m src.sync_to_aws

sync-learnerlab-dry:
	@test -f .env.learnerlab || { echo "Missing .env.learnerlab — copy from .env.learnerlab.example and fill in values"; exit 1; }
	env $$(grep -v '^#' .env.learnerlab | xargs) python -m src.sync_to_aws --dry-run

## Sync to BOTH environments sequentially
sync-all: sync-freetier sync-learnerlab
	@echo "=== Done syncing to all environments ==="

## Legacy: uses current shell env vars (backward-compat)
sync-aws:
	python -m src.sync_to_aws

sync-aws-dry:
	python -m src.sync_to_aws --dry-run

sync-s3:
	python -m src.sync_to_aws --s3-only

sync-db:
	python -m src.sync_to_aws --db-only
