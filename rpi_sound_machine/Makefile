MAKEFILE_SETTINGS_FILE := /tmp/makefile_settings.mk

.PHONY: $(MAKEFILE_SETTINGS_FILE) kill-tmux
$(MAKEFILE_SETTINGS_FILE):
	python device_tool.py --make-settings-file

include $(MAKEFILE_SETTINGS_FILE)

TMUX_LOG ?= true
TMUX_ATTACH ?= true

#.PHONY: no_arguments stop install run reboot

no_arguments:
	@echo "Provide arguments: install | run | stop"

stop:
	@echo "Stopping application. (placeholder - not implemented yet)"

kill-tmux:
	@echo "Killing tmux session: $(TMUX_SESSION_NAME)"
	@echo "$(TMUX_LOG_FILE)"

	-@tmux kill-session -t $(TMUX_SESSION_NAME) 2>/dev/null
	-@rm -f /tmp/$(TMUX_SESSION_NAME)-tmux_*.log 2>/dev/null

install: stop kill-tmux
	@echo "Installing needed applications and restarting application service."
	@python device_tool.py -y --restart-service

run: stop kill-tmux
	@echo "Starting new tmux session '$(TMUX_SESSION_NAME)'"
	@tmux new-session -d -s $(TMUX_SESSION_NAME)
	@tmux send-keys -t $(TMUX_SESSION_NAME):0.0 "uv run --no-group dev $(APPLICATION_FILE)" C-m
	ifeq ($(TMUX_LOG),true)
		@echo "Configuring tmux logging."
		@tmux pipe-pane -t $(TMUX_SESSION_NAME):0.0 -o "cat >> $(TMUX_LOG_FILE)"
	endif
	ifeq ($(TMUX_ATTACH),true)
		@echo "Attaching to tmux session: $(TMUX_SESSION_NAME)"
		@tmux attach -t $(TMUX_SESSION_NAME)
	endif

reboot:
	@echo "Rebooting device."