#!/bin/bash
APPLICATION_DIRECTORY="rpi_sound_machine"
TMUX_SESSION_NAME="sound"
TMUX_LOG_FILE_PATH_PATTERN="/tmp/${TMUX_SESSION_NAME}-tmux_{timestamp}.log"

cd ~/"${APPLICATION_DIRECTORY}"
tmux kill-session -t "${TMUX_SESSION_NAME}" 2>/dev/null
## rm -f ${TMUX_LOG_FILE_PATH_PATTERN/\{timestamp\}/*} 2>/dev/null  # Remove old tmux logs
tmux new-session -d -s "${TMUX_SESSION_NAME}"

if [ "$1" == "tmux-log" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    TMUX_LOG_FILE="${TMUX_LOG_FILE_PATH_PATTERN/\{timestamp\}/$TIMESTAMP}"
    tmux pipe-pane -t "${TMUX_SESSION_NAME}":0.0 -o "cat >> \"${TMUX_LOG_FILE}\""
fi  

tmux send-keys -t sound "uv run --no-group dev sound_machine.py" C-m

## tmux attach-session -t "${TMUX_SESSION_NAME}"
