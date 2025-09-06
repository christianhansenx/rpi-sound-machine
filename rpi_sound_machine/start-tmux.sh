#!/bin/bash
cd ~/rpi_sound_machine
tmux_session_name="sound"
tmux kill-session -t "$tmux_session_name" 2>/dev/null
rm /tmp/rpi_sound_machine.tmux-log 2>/dev/null
tmux new-session -d -s "$tmux_session_name"
tmux pipe-pane -t "$tmux_session_name":0.0 -o "cat >> /tmp/rpi_sound_machine.tmux-log"