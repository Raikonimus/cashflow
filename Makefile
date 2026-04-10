# ─── CashFlow Dev-Server Makefile ─────────────────────────────────────────────
#
# Nutzung:
#   make start    – Backend + Frontend starten (Logs in .run/*.log)
#   make stop     – Beide Services stoppen
#   make restart  – stop + start
#   make status   – Zeigt ob Prozesse laufen
#   make logs     – Verfolgt beide Logfiles gleichzeitig
#   make test     – Alle Tests (Backend + Frontend)
#   make migrate  – Alembic-Migrationen ausführen
#

SHELL := /bin/zsh
ROOT  := $(shell pwd)

BACKEND_DIR  := $(ROOT)/backend
FRONTEND_DIR := $(ROOT)/frontend
VENV         := $(BACKEND_DIR)/.venv

RUN_DIR := $(ROOT)/.run
BACKEND_PID  := $(RUN_DIR)/backend.pid
FRONTEND_PID := $(RUN_DIR)/frontend.pid
BACKEND_LOG  := $(RUN_DIR)/backend.log
FRONTEND_LOG := $(RUN_DIR)/frontend.log

UVICORN := $(VENV)/bin/uvicorn
NPM     := npm

# ─── Start ────────────────────────────────────────────────────────────────────

.PHONY: start
start: _ensure-run-dir _start-backend _start-frontend
	@echo ""
	@echo "✅  Dienste gestartet:"
	@echo "    Backend   → http://localhost:8000  (Logs: .run/backend.log)"
	@echo "    Frontend  → http://localhost:5173  (Logs: .run/frontend.log)"
	@echo ""
	@echo "    make stop    – Dienste stoppen"
	@echo "    make logs    – Live-Logs verfolgen"

.PHONY: _start-backend
_start-backend:
	@if [ -f "$(BACKEND_PID)" ] && kill -0 $$(cat "$(BACKEND_PID)") 2>/dev/null; then \
		echo "⚠   Backend läuft bereits (PID $$(cat $(BACKEND_PID)))"; \
	else \
		echo "▶   Backend starten …"; \
		cd "$(BACKEND_DIR)" && \
		  nohup $(UVICORN) app.main:app \
		    --host 0.0.0.0 --port 8000 \
		    --reload \
		    > "$(BACKEND_LOG)" 2>&1 & \
		  echo $$! > "$(BACKEND_PID)"; \
		echo "    PID $$(cat $(BACKEND_PID))"; \
	fi

.PHONY: _start-frontend
_start-frontend:
	@if [ -f "$(FRONTEND_PID)" ] && kill -0 $$(cat "$(FRONTEND_PID)") 2>/dev/null; then \
		echo "⚠   Frontend läuft bereits (PID $$(cat $(FRONTEND_PID)))"; \
	else \
		echo "▶   Frontend starten …"; \
		cd "$(FRONTEND_DIR)" && \
		  nohup $(NPM) run dev \
		    > "$(FRONTEND_LOG)" 2>&1 & \
		  echo $$! > "$(FRONTEND_PID)"; \
		echo "    PID $$(cat $(FRONTEND_PID))"; \
	fi

# ─── Stop ─────────────────────────────────────────────────────────────────────

.PHONY: stop
stop: _stop-backend _stop-frontend
	@echo "🛑  Alle Dienste gestoppt."

.PHONY: _stop-backend
_stop-backend:
	@if [ -f "$(BACKEND_PID)" ]; then \
		PID=$$(cat "$(BACKEND_PID)"); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "■   Backend stoppen (PID $$PID) …"; \
			kill $$PID; \
		else \
			echo "    Backend war bereits gestoppt."; \
		fi; \
		rm -f "$(BACKEND_PID)"; \
	else \
		echo "    Backend-PID nicht gefunden."; \
	fi

.PHONY: _stop-frontend
_stop-frontend:
	@if [ -f "$(FRONTEND_PID)" ]; then \
		PID=$$(cat "$(FRONTEND_PID)"); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "■   Frontend stoppen (PID $$PID) …"; \
			kill $$PID; \
		else \
			echo "    Frontend war bereits gestoppt."; \
		fi; \
		rm -f "$(FRONTEND_PID)"; \
	else \
		echo "    Frontend-PID nicht gefunden."; \
	fi

# ─── Restart ──────────────────────────────────────────────────────────────────

.PHONY: restart
restart: stop start

# ─── Status ───────────────────────────────────────────────────────────────────

.PHONY: status
status:
	@echo "── Dienst-Status ──────────────────────────────"
	@if [ -f "$(BACKEND_PID)" ] && kill -0 $$(cat "$(BACKEND_PID)") 2>/dev/null; then \
		echo "  Backend   ✅  läuft  (PID $$(cat $(BACKEND_PID)))"; \
	else \
		echo "  Backend   ❌  gestoppt"; \
	fi
	@if [ -f "$(FRONTEND_PID)" ] && kill -0 $$(cat "$(FRONTEND_PID)") 2>/dev/null; then \
		echo "  Frontend  ✅  läuft  (PID $$(cat $(FRONTEND_PID)))"; \
	else \
		echo "  Frontend  ❌  gestoppt"; \
	fi
	@echo "────────────────────────────────────────────────"

# ─── Logs ─────────────────────────────────────────────────────────────────────

.PHONY: logs
logs:
	@echo "Zeige Logs (Ctrl+C zum Beenden) …"
	@tail -n 30 -f "$(BACKEND_LOG)" "$(FRONTEND_LOG)"

.PHONY: logs-backend
logs-backend:
	@tail -f "$(BACKEND_LOG)"

.PHONY: logs-frontend
logs-frontend:
	@tail -f "$(FRONTEND_LOG)"

# ─── Tests ────────────────────────────────────────────────────────────────────

.PHONY: test
test: test-backend test-frontend

.PHONY: test-backend
test-backend:
	@echo "▶   Backend-Tests …"
	@cd "$(BACKEND_DIR)" && $(VENV)/bin/python -m pytest -q

.PHONY: test-frontend
test-frontend:
	@echo "▶   Frontend-Tests …"
	@cd "$(FRONTEND_DIR)" && npx vitest run

# ─── Migrationen ──────────────────────────────────────────────────────────────

.PHONY: migrate
migrate:
	@echo "▶   Alembic-Migrationen …"
	@cd "$(BACKEND_DIR)" && $(VENV)/bin/alembic upgrade head

.PHONY: migrate-status
migrate-status:
	@cd "$(BACKEND_DIR)" && $(VENV)/bin/alembic current

# ─── Hilfsziel ────────────────────────────────────────────────────────────────

.PHONY: _ensure-run-dir
_ensure-run-dir:
	@mkdir -p "$(RUN_DIR)"
