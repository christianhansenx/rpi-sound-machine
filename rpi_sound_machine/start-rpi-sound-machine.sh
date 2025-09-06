#!/bin/bash
tmux kill-session -t sound 2>/dev/null
rm /tmp/rpi_sound_machine.tmux-log 2>/dev/null
tmux new-session -d -s sound
tmux pipe-pane -t sound:0.0 -o "cat >> /tmp/rpi_sound_machine.tmux-log"
tmux send-keys -t sound 'cd /home/pi/rpi_sound_machine && ./start.sh' C-m
