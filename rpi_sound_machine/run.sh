#!/bin/bash
set -e

APPLICATION_DIRECTORY="rpi_sound_machine"
cd ~/"${APPLICATION_DIRECTORY}"

SETTINGS_FILE="settings.yaml"
TMUX_SESSION_NAME=$(yq -r ".tmux.session_name" "$SETTINGS_FILE")

set +e
tmux kill-session -t "${TMUX_SESSION_NAME}" 2>/dev/null
rm -f ${TMUX_LOG_FILE_PATH_PATTERN/\{timestamp\}/*} 2>/dev/null  # Remove old tmux logs
set -e

tmux new-session -d -s "${TMUX_SESSION_NAME}"

if [ "$1" == "tmux-log" ]; then
    SETTING_TMUX_LOG_FILE_PATH_PATTERN=$(yq ".tmux.log_file_path_pattern" "$SETTINGS_FILE")
    TMUX_LOG_FILE_PATH_PATTERN=${SETTING_TMUX_LOG_FILE_PATH_PATTERN/\{session_name\}/$TMUX_SESSION_NAME}
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    TMUX_LOG_FILE="${TMUX_LOG_FILE_PATH_PATTERN/\{timestamp\}/$TIMESTAMP}"
    tmux pipe-pane -t "${TMUX_SESSION_NAME}":0.0 -o "cat >> \"${TMUX_LOG_FILE}\""
fi  

tmux send-keys -t "${TMUX_SESSION_NAME}:0.0" "uv run --no-group dev sound_machine.py" C-m

if [ "$1" == "tmux-attach" ]; then
    tmux attach -t "${TMUX_SESSION_NAME}"
fi
