#!/bin/bash
TMUX_SESSION_NAME="sound"

cd ~/rpi_sound_machine
tmux kill-session -t "$TMUX_SESSION_NAME" 2>/dev/null
rm /tmp/rpi_sound_machine.tmux-log 2>/dev/null
tmux new-session -d -s "$TMUX_SESSION_NAME"; tmux pipe-pane -t "$TMUX_SESSION_NAME":0.0 -o "cat >> /tmp/rpi_sound_machine.tmux-log"
