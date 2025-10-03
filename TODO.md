# TODO (features and improvements)

## Improvements

- create issues in github
- continue current play after reboot / status log in browser of when it was started last 20 times
- avoid restart service when exit ssh session
- scli command<br>
  create a symbolic link (symlink) to your script in a directory already in your PATH, like /usr/local/bin.<br>
  sudo ln -s /path/to/your_script.py /usr/local/bin/cli<br>
  This command creates a link named cli in /usr/local/bin that points to your script. Now, you can run cli from any directory.<br>
- make it possible for service to start with make start
- setting up github to run test at pull request
- refactor and document install and uninstall items (also implement --exclude (add apt_get_update as item)), get Killsignal enums
- tools check to check system service and tmux session and tmux log.
- remote install and reboot (just rpi install, boot, off)
- graceful stop of rpi app via rpi_remote.py (stop service if it is running)
- locate files in ~/.config on the RPI
- python code to ask local time location and update rpi with it
- provide as configs to RPI remote tools:<br>
UPLOAD_EXCLUDES_FOLDERS = ['.venv', '.git', '.ruff_cache', '__pycache__']<br>
UPLOAD_EXCLUDES_FILES = []  # Add specific file names here if needed
- connect to bt speaker
- mypy or Pyright
- ruff HTML, CSS, JS
- rotate .tmux-log
- ram disk for .tmux-log
- progress bar for uploading files
- scrollable file lists
- light blue background
- volume adjust each clip and save as multi sound to file

## Bugs

- Stop and Pause button is not disabled when no sounds are activated
- If all sounds are deactivated during pause then Play button is still displayed
- Bin button should be disabled when no files selected
- It takes several seconds from starting sound to it is indicated with bold font
- Error when start plying new sound:<br>
192.168.10.102 - - [01/Sep/2025 21:47:35] "GET /toggle_play/aircraft-cabin-sound-129404.mp3 HTTP/1.1" 200<br>
ALSA lib pcm.c:8570:(snd_pcm_recover) underrun occurred
