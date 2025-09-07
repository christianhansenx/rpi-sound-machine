#!/bin/bash
cd ~/rpi_sound_machine
tmux send-keys -t sound "uv run --no-group dev sound_machine.py" C-m
