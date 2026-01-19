# Raspberry Pi Sound Machine with Browser Interface

This project turns a Raspberry Pi into a customizable sound machine.<br>
User can upload own sound files and play them through a web interface, creating a personalized soundscape to mask unwanted
 noise or for relaxation.<br>
The interface allows playing multiple sounds simultaneously.
The sounds are looping infinitely.

![sound-machine](sound_machine.jpg)

## Background idea of this project

Sometimes there's a very low-frequency noise in my apartment, which I believe is coming from installations or equipment in the
 building. This can be very disturbing.
It inspired me making this sound machine for playing relaxing sounds that help drown out the low hum.

In general the issue about low-frequency hum is a quite widespread problem:
 [Noise & Health](https://journals.lww.com/nohe/fulltext/2004/06230/low_frequency_noise_and_annoyance.6.aspx)

## User Guide

Connect Raspberry Pi to a loudspeaker (loudspeaker with aux input).<br>
*Note: in this user guide the Raspberry Pi hostname is **pisound** (it can be any name you choose).*


Copy **rpi_sound_machine** folder from this repository to Raspberry Pi device **/home/~** folder.<br>
Then ssh into the Raspberry Pi device and **cd** to **/home/~/rpi_sound_machine** folder.

Install necessary applications with:<br>
```make install```

 and start sound machine service with:<br>
```make start-service```

The Raspberry Pi Sound Machine is to be controlled via local network through browser: ***pisound:5000***

### Web Interface

#### Uploading Sounds

1. Click the "Choose Files" button in the "Upload Sound Files" section.
2. Select one or more sound files from your computer.
3. Click the "Upload" button to upload them to the Raspberry Pi.

I found some good sounds here: [Pixabay Free Sounds](https://pixabay.com/sound-effects/search/)

#### Playing Sounds

* **Play a sound**: Click on the name of a sound file in the "Sound Files" list to start playing it.
 The sound will loop continuously.
* **Play multiple sounds**: You can play multiple sounds at the same time by clicking on additional sound files.

#### Controls

At the top of the page, you'll find control buttons:

* **Pause/Resume (⏸️/▶️)**: Click to pause or resume all currently playing sounds.
* **Stop (⏹️)**: Click to stop all sounds.
* **Delete (🗑️)**: To delete files, check the boxes next to the file names you want to delete, then click this button.

#### Timer

A timer at the top of the page (below control buttons) shows how long the currently playing sounds have been active.

## Development guide

### Install UV on PC

Install **uv** according to:
 [installation of uv](https://github.com/christianhansenx/hansen-developer-notes/blob/main/tools-and-apps/uv/README.MD)

### Install "just" on PC

Install **just** according to:
 [installation of just](https://github.com/christianhansenx/hansen-developer-notes/blob/main/tools-and-apps/just/README.MD)

Too see list of **just** recipes, execute **just** without recipe argument: ```just```

If you are on Windows, then run the **just** recipes in Git Bash (download from  [git](https://git-scm.com/))<br>
[Setting up VS code to use Git Bash terminal](https://github.com/christianhansenx/hansen-developer-notes/blob/main/tools-and-apps/vs-code/README.MD#windows---git-bash-terminal)

### Interfacing with Raspberry Pi from PC

Instead of having to do manually SSH into the RPI, then many operations can be applied by using the **just rpi** recipes in
 **rpi-remote-tools/justfile**.<br>
To get a list of RPI remote tool commands then execute ```just rpi``` (on the PC) without arguments.

Example of running a command: ```just rpi check```.
```
Python version: 3.13
Create SSH connection to pi@pisound

== Remote command to RPI: make check
python developer_tools/application_utilities.py --check
UTC time: 2026-01-18 16:28:47
Python version: 3.13
System service "sound-machine.service" status: running
  ● sound-machine.service - Sound Machine
       Loaded: loaded (/etc/systemd/system/sound-machine.service; enabled; preset: enabled)
       Active: active (running) since Sun 2026-01-18 16:28:14 UTC; 33s ago
   Invocation: 5b5f1252b67e42078ddfa41ee3fa4bfb
     Main PID: 11990 (sound-machine-s)
        Tasks: 10 (limit: 759)
          CPU: 7.995s
       CGroup: /system.slice/sound-machine.service
               ├─11990 /bin/bash /usr/local/bin/sound-machine-start.sh
               ├─11991 /snap/astral-uv/1258/bin/uv run --no-group dev sound_machine.py
               └─12072 /home/pi/rpi_sound_machine/.venv/bin/python3 sound_machine.py

  Jan 18 16:28:28 pisound sound-machine-start.sh[12072]: UTC time: 2026-01-18 16:28:28
  Jan 18 16:28:28 pisound sound-machine-start.sh[12072]: Python version: 3.13
  Jan 18 16:28:28 pisound sound-machine-start.sh[12072]: Volume file not found, using default 0.5
Running processes of "sound_machine.py":
  USER         PID %CPU %MEM    VSZ   RSS TTY   STAT START   TIME COMMAND
  pi         11991 10.8  4.2 613312 39084 ?     Sl   16:28   0:03 /snap/astral-uv/1258/bin/uv run --no-group dev sound_machine.py
  pi         12072 17.6  5.1 236368 48228 ?     Sl   16:28   0:04 /home/pi/rpi_sound_machine/.venv/bin/python3 sound_machine.py
Tmux session "sound": session does not exist
```

Some of the connections to the RPI are using [tmux](https://github.com/tmux/tmux/wiki) terminal on the RPI.<br>
When running tmux from tools terminal, it can be stopped by pressing **enter** key.
