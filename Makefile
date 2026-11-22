# Monorepo entry point. Prism targets run inside apps/prism; swarm helpers live in apps/swarm.
PRISM := apps/prism
SWARM := apps/swarm

.PHONY: help dev dev-all setup check release-check swarm-setup swarm-dev \
	setup dev migrate test test-integration test-e2e lint format format-check typecheck secrets audit \
	frontend-install frontend-build frontend-dev frontend-check frontend-types

help:
	@echo "Prism targets (run in apps/prism): setup dev migrate test test-integration test-e2e lint format format-check typecheck secrets audit check release-check"
	@echo "Dashboard (apps/prism/frontend): frontend-install frontend-build frontend-dev frontend-check frontend-types"
	@echo "dev-all      Prism (8000) + swarm API (8080) + swarm worker, one command"
	@echo "swarm-setup  Install swarm Python dependencies and set up its database"
	@echo "swarm-dev    Run swarm API, worker and demo shop on their own"

dev-all:
	./scripts/dev.sh

swarm-setup:
	cd $(SWARM) && ./scripts/setup.sh

swarm-dev:
	cd $(SWARM) && ./scripts/dev.sh

# Everything else is forwarded to apps/prism/Makefile.
setup dev migrate test test-integration test-e2e lint format format-check typecheck secrets audit check release-check frontend-install frontend-build frontend-dev frontend-check frontend-types:
	$(MAKE) -C $(PRISM) $@
