#!/bin/bash
cd ~/rpi_sound_machine
tmux send-keys -t sound "uv run --no-group dev main.py" C-m
