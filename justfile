# Path relative to the justfile's location
TOOLS_PATH := "tools"


# Executing "just" without arguments is listing all recipes
list-recipes:
    @just --list --unsorted

# RPI: Checking about application is already running on Raspberry Pi device
check:
    @uv run --quiet --project "{{TOOLS_PATH}}" python "{{TOOLS_PATH}}"/tools.py --rpi-check-app

# RPI: Killing running application on Raspberry Pi device
kill:
    @uv run --quiet --project "{{TOOLS_PATH}}" python "{{TOOLS_PATH}}"/tools.py --rpi-kill-app

# RPI: Starting application on Raspberry Pi device (first it will kill already running app) 
run:
    @uv run --quiet --project "{{TOOLS_PATH}}" python "{{TOOLS_PATH}}"/tools.py --rpi-run-app

# RPI: Copying application to Raspberry Pi device and then starting application
sync:
    @uv run --quiet --project "{{TOOLS_PATH}}" python "{{TOOLS_PATH}}"/tools.py --rpi-copy-code

# RPI: Live stream from Raspberry Pi device tmux session
tmux:
    @uv run --quiet --project "{{TOOLS_PATH}}" python "{{TOOLS_PATH}}"/tools.py --rpi-tmux

# Check linting with ruff
ruff:
    @uv run --quiet ruff check

# Fix linting with ruff
ruff-fix:
    @uv run --quiet ruff check --fix

# Run unit tests
test:
    @uv run --quiet --project rpi_sound_machine --active python -m pytest -vvv
