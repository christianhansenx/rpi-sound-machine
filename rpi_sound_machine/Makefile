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
	@echo "Stopping application."
	@python device_tool.py -y --stop-application

kill-tmux: $(MAKEFILE_SETTINGS_FILE) stop
	@echo "Killing tmux session: $(TMUX_SESSION_NAME)"
	-@tmux kill-session -t $(TMUX_SESSION_NAME) 2>/dev/null
	-@rm -f $(TMUX_LOG_FILES) 2>/dev/null

install: kill-tmux
	@echo "Installing applications and restarting application service."
	@python device_tool.py -y -i --stop-application --restart-service

#run: stop kill-tmux
run: $(MAKEFILE_SETTINGS_FILE) kill-tmux
	@echo "Running $(APPLICATION_SCRIPT) in a new tmux session '$(TMUX_SESSION_NAME)'"
	@tmux new-session -d -s $(TMUX_SESSION_NAME)
	@tmux send-keys -t $(TMUX_SESSION_NAME):0.0 "uv run --no-group dev $(APPLICATION_SCRIPT)" C-m
ifeq ($(TMUX_LOG), true)
	@echo "Configuring tmux logging."
	@tmux pipe-pane -t $(TMUX_SESSION_NAME):0.0 -o "cat >> $(TMUX_LOG_FILE)"
endif
	@echo
	@echo "TO ENTER TMUX TERMINAL: tmux attach -t $(TMUX_SESSION_NAME)"

reboot:
	@echo "Rebooting device."
	@sudo reboot
