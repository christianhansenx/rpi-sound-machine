# Executing "just" without arguments is listing all recipes
list-recipes:
    @just --list --unsorted

RPI_REMOTE_TOOLS_PATH := "rpi-remote-tools"
RPI_REMOTE_TOOLS_CONFIG_FILE := "rpi_remote_tools_config.yaml"
# Raspberry Pi Remote Tools recipes.
rpi rpi_args="":
    @if [ -n "{{rpi_args}}" ]; then \
        just --justfile {{RPI_REMOTE_TOOLS_PATH}}/justfile \
            {{rpi_args}} config_file_arg={{RPI_REMOTE_TOOLS_CONFIG_FILE}}; \
    else \
        just --justfile {{RPI_REMOTE_TOOLS_PATH}}/justfile; \
    fi

# Check linting with ruff
ruff:
    @uv run --quiet ruff check

# Fix linting with ruff
ruff-fix:
    @uv run --quiet ruff check --fix

# Run unit tests
test:
    @uv run --quiet --project rpi_sound_machine --active python -m pytest -vvv
