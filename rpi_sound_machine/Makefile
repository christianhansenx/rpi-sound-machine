MAKEFILE_SETTINGS_FILE := settings.mk
include $(MAKEFILE_SETTINGS_FILE)
TIMESTAMP := $(shell date -u +%Y%m%d_%H%M%S)
TMUX_LOG_FILE := $(subst {timestamp},$(TIMESTAMP),$(TMUX_LOG_FILE_PATTERN))
TMUX_LOG_FILES := $(wildcard $(subst {timestamp},*,$(TMUX_LOG_FILE_PATTERN)))

TMUX_LOG ?= true
TMUX_ATTACH ?= true


# Define your phony targets.
.PHONY: no_arguments stop kill-tmux install run reboot

no_arguments:
	@echo "Missing argument. Arguments: install | run | stop"

process-id:
	@python device_tool.py --get-application-process-ids

stop:
	@python device_tool.py --stop-application


kill-tmux:
	python device_tool.py --kill-tmux

restart-service:
	python device_tool.py --restart-service

install: kill-tmux
	@echo "Installing applications and restarting application service."
	@python device_tool.py -y -i --stop-application --restart-service

#run: stop kill-tmux
run: $(MAKEFILE_SETTINGS_FILE) kill-tmux
	@echo "Running $(APPLICATION_SCRIPT) in a new tmux session '$(TMUX_SESSION_NAME)'"
	@tmux new-session -d -s $(TMUX_SESSION_NAME)
ifeq ($(TMUX_LOG), true)
	@echo "Configuring tmux logging to $(TMUX_LOG_FILE)."
	@mkdir -p $(dir $(TMUX_LOG_FILE))
	@touch $(TMUX_LOG_FILE)
	@tmux pipe-pane -t $(TMUX_SESSION_NAME):0.0 -o "cat >> $(TMUX_LOG_FILE)"
endif
	@tmux send-keys -t $(TMUX_SESSION_NAME):0.0 "uv run --no-group dev $(APPLICATION_SCRIPT)" C-m
	@echo
	@echo "TO ENTER TMUX TERMINAL: tmux attach -t $(TMUX_SESSION_NAME)"

reboot:
	@echo "Rebooting device."
	@sudo reboot
