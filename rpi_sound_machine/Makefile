# Define variables to get the session name from the YAML file.
# The `shell` function executes a command and uses its output.
SETTINGS_FILE := settings.yaml
TMUX_SESSION_NAME := $(shell yq -r ".tmux.session_name" $(SETTINGS_FILE))
APPLICATION_FILE := $(shell yq -r ".application_file" $(SETTINGS_FILE))

# This will set the variable if it's not provided on the command line.
TMUX_LOG ?= true
TMUX_ATTACH ?= true

# Define phony targets to ensure they are always run as commands,
# not as files.
.PHONY: no_arguments clean start log attach

no_arguments:
	@echo "Provide arguments: start | log | attach"

# The 'clean' target kills the tmux session and removes old logs.
# The '-' prefix on the commands prevents `make` from exiting if they fail.
clean:
	@echo "Cleaning up old tmux sessions and logs..."
	-@tmux kill-session -t $(TMUX_SESSION_NAME) 2>/dev/null
	-@rm -f /tmp/$(TMUX_SESSION_NAME)-tmux_*.log 2>/dev/null

# The 'start' target creates and initializes the tmux session.
# This target is a prerequisite for 'log' and 'attach'.
start: clean
	@echo "Starting new tmux session '$(TMUX_SESSION_NAME)'..."
	@tmux new-session -d -s $(TMUX_SESSION_NAME)
	@tmux send-keys -t $(TMUX_SESSION_NAME):0.0 "uv run --no-group dev $(APPLICATION_FILE)" C-m

# Conditionally configure logging if the TMUX_LOG variable is set to 'true'.
ifeq ($(TMUX_LOG),true)
	@echo "Configuring tmux logging..."
	@tmux pipe-pane -t $(TMUX_SESSION_NAME):0.0 -o "cat >> \"$(shell yq -r ".tmux.log_file_path_pattern" $(SETTINGS_FILE) | sed "s/{session_name}/$(TMUX_SESSION_NAME)/g" | sed "s/{timestamp}/$(shell date +%Y%m%d_%H%M%S)/g")\""
endif

# Conditionally attach to the session if the TMUX_ATTACH variable is set to 'true'.
ifeq ($(TMUX_ATTACH),true)
	@echo "Attaching to tmux session '$(TMUX_SESSION_NAME)'..."
	@tmux attach -t $(TMUX_SESSION_NAME)
endif

# The 'log' target configures session logging.
# It depends on 'start' to ensure the session exists.
log:
	@echo "Configuring tmux logging..."
	@tmux pipe-pane -t $(TMUX_SESSION_NAME):0.0 -o "cat >> \"$(shell yq -r ".tmux.log_file_path_pattern" $(SETTINGS_FILE) | sed "s/{session_name}/$(TMUX_SESSION_NAME)/g" | sed "s/{timestamp}/$(shell date +%Y%m%d_%H%M%S)/g")\""

# The 'attach' target attaches to the running tmux session.
# It depends on 'start' to ensure the session exists.
attach:
	@echo "Attaching to tmux session '$(TMUX_SESSION_NAME)'..."
	@tmux attach -t $(TMUX_SESSION_NAME)
