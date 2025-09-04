# Raspberry Pi Sound Machine with Browser Interface

![sound-machine](sound_machine.jpg)

## Background idea of this project

Sometimes there's a very low-frequency noise in my apartment, which I believe is coming from the building's heating system. It's disturbing my sleep, so I now use a sound machine to play relaxing sounds that help drown out the low hum.

In general the issue about low-frequency hum is a quite widespread problem: [Noise & Health](https://journals.lww.com/nohe/fulltext/2004/06230/low_frequency_noise_and_annoyance.6.aspx)

## User Guide

Connect Raspberry Pi to a loudspeaker (loudspeaker with aux input).

Install uv python package installer: [Install uv on RPI with Snap](https://snapcraft.io/install/astral-uv/raspbian)

Copy **rpi_sound_machine** folder to Raspberry Pi and run it with uv in **rpi_sound_machine** folder:<br>
```uv run --no-group dev sound_machine.py```

The Raspberry Pi Sound Machine makes it possible to control sound playing on Raspberry Pi through a web interface: *raspberry-pi-hostname*:5000

### Web Interface

#### Playing Sounds

*   **Play a sound**: Click on the name of a sound file in either the "Sound Files" or "Favorites" list to start playing it. The sound will loop continuously.
*   **Play multiple sounds**: You can play multiple sounds at the same time by clicking on additional sound files.

#### Favorites

*   **Add to favorites**: To add a sound to your favorites, click 🤍 next to the file name.
*   **Remove from favorites**: To remove a sound from your favorites, click ❤️ next to the file name in the "Favorites" list.

#### Controls

At the top of the page, you'll find control buttons:

*   **Pause/Resume (⏸️/▶️)**: Click to pause or resume all currently playing sounds.
*   **Stop (⏹️)**: Click to stop all sounds.
*   **Delete (🗑️)**: To delete files, check the boxes next to the file names you want to delete, then click this button.

#### Timer

A timer at the top of the page (below control buttons) shows how long the currently playing sounds have been active.

#### Uploading Sounds

1.  Click the "Choose Files" button under.
2.  Select one or more sound files from your computer.
3.  Click the "Upload" button to upload them to the Raspberry Pi.

I found some good sounds here: [Pixabay Free Sounds](https://pixabay.com/sound-effects/search/)

## Development guide

### Install UV on PC

Install **uv** according to: [installation of uv](https://github.com/christianhansenx/hansen-developer-notes/blob/main/tools-and-apps/uv/README.MD)

### Install "just" on PC

Install **just** according to: [installation of just](https://github.com/christianhansenx/hansen-developer-notes/blob/main/tools-and-apps/just/README.MD)

Too see list of **just** recipes, execute **just** without recipe argument: ```just```

If you are on Windows, then run the **just** recipes in Git Bash (download from  [git](https://git-scm.com/))<br>
[Setting up VS code to use Git Bash terminal](https://github.com/christianhansenx/hansen-developer-notes/blob/main/tools-and-apps/vs-code/README.MD#windows---git-bash-terminal)

### Interfacing with Raspberry Pi from PC

Instead of having to do manually SSH into the RPI, then many operations can be applied by using the **just rpi** recipes in **rpi-remote-tools/justfile**.<br>
To get a list of RPI remote tool commands then execute ```just rpi``` without arguments.

Some of the connections to the RPI is using [tmux](https://github.com/tmux/tmux/wiki) terminal on the RPI.<br>

When running tmux from tools terminal, it can be stopped by pressing **enter** key.
