"""Raspberry Pi Sound Machine - A web-based sound machine using Flask and Pygame."""
import json
import time
from pathlib import Path
from threading import Timer

import pygame
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename
from werkzeug.wrappers import Response as BaseResponse

# Initialize Flask app
app = Flask(__name__)

# Initialize Pygame mixer
pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=2048)
pygame.mixer.init()
pygame.mixer.set_num_channels(16)

# Define the directory where your sound files are stored
SOUND_DIR = Path(__file__).parent.parent / 'sounds'
# Define the path for the favorites file
FAVORITES_FILE = Path(__file__).parent.parent / 'favorites.txt'
# Define the path for the volume file
VOLUME_FILE = Path(__file__).parent.parent / 'volume.json'

DEFAULT_GLOBAL_VOLUME = 0.5  # 0.0 to 1.0


class SoundControl:
    """Class to manage sound control state and operations."""

    def __init__(self) -> None:
        """Initialize control settings."""
        self.global_volume = DEFAULT_GLOBAL_VOLUME
        self.volume_save_timer = None
        self.paused = False
        self.current_sounds = set()
        self.elapsed_time_at_pause = 0
        self.last_play_time = None
        self.sound_objects = {}

    def get_state_as_dict(self) -> dict[str, object]:
        """Return the current state of the SoundControl.

        Returns:
            State as JSON-serializable dictionary.

        """
        return {
            'paused': self.paused,
            'last_play_time': self.last_play_time,
            'elapsed_time_at_pause': self.elapsed_time_at_pause,
            'active_sounds': sorted(self.current_sounds),
            'volume': self.global_volume,
        }

    def load_volume(self) -> None:
        if VOLUME_FILE.is_file():
            try:
                with Path.open(VOLUME_FILE) as f:
                    data = json.load(f)
                    self.global_volume = float(data.get('volume', DEFAULT_GLOBAL_VOLUME))
            except (OSError, json.JSONDecodeError):
                print(f'Error loading volume file, using default {DEFAULT_GLOBAL_VOLUME}')
        else:
            print(f'Volume file not found, using default {DEFAULT_GLOBAL_VOLUME}')

    def save_volume(self) -> None:
        with Path.open(VOLUME_FILE, 'w') as f:
            json.dump({'volume': self.global_volume}, f)
        print(f'Volume saved to file: {self.global_volume}')

    def schedule_volume_save(self) -> None:
        if self.volume_save_timer:
            self.volume_save_timer.cancel()
        self.volume_save_timer = Timer(5.0, self.save_volume)
        self.volume_save_timer.start()

    @staticmethod
    def get_favorites() -> set[str]:
        if not FAVORITES_FILE.is_file():
            return set()
        with Path.open(FAVORITES_FILE) as f:
            return {line.strip() for line in f}

    @staticmethod
    def save_favorites(favorites_set: set[str]) -> None:
        with Path.open(FAVORITES_FILE, 'w') as f:
            f.writelines(f'{filename}\n' for filename in sorted(favorites_set))


sound_control = SoundControl()


@app.route('/')
def home() -> BaseResponse:
    all_files = [f.name for f in SOUND_DIR.glob('*') if f.is_file()]
    favorites_set = sound_control.get_favorites()

    # Separate the files into favorites and non-favorites
    favorite_files = sorted([f for f in all_files if f in favorites_set])
    non_favorite_files = sorted([f for f in all_files if f not in favorites_set])

    sound_state = sound_control.get_state_as_dict()

    return render_template(
        'index.html',
        sound_state=sound_state,
        sound_files=non_favorite_files,
        favorites=favorite_files,
    )


@app.route('/pause_resume')
def pause_resume() -> BaseResponse:
    if not sound_control.paused:
        # Pause all sounds
        pygame.mixer.pause()
        sound_control.paused = True
        if sound_control.last_play_time is not None:
            sound_control.elapsed_time_at_pause += time.time() - sound_control.last_play_time
            sound_control.last_play_time = None
    else:
        # Resume all sounds
        pygame.mixer.unpause()
        sound_control.paused = False
        if sound_control.elapsed_time_at_pause > 0:
            sound_control.last_play_time = time.time()
    return jsonify(sound_control.get_state_as_dict())


@app.route('/set_volume/<float:volume_level>')
def set_volume(volume_level: float) -> BaseResponse:
    # Set the volume for all currently playing sounds
    sound_control.global_volume = volume_level
    for snd in sound_control.sound_objects.values():
        snd.set_volume(sound_control.global_volume)

    sound_control.schedule_volume_save()

    data = sound_control.get_state_as_dict()
    data['success'] = True
    return jsonify(data)


@app.route('/toggle_play/<sound_file>')
def toggle_play(sound_file: str) -> BaseResponse:
    sound_path = SOUND_DIR / sound_file

    if sound_file in sound_control.current_sounds:
        if sound_file in sound_control.sound_objects:
            sound_control.sound_objects[sound_file].stop()
            del sound_control.sound_objects[sound_file]
        sound_control.current_sounds.remove(sound_file)

        if not sound_control.current_sounds:
            sound_control.last_play_time = None
            sound_control.elapsed_time_at_pause = 0
            sound_control.paused = False
    elif sound_path.is_file():
        try:
            snd = pygame.mixer.Sound(str(sound_path))
            snd.play(loops=-1)
            snd.set_volume(sound_control.global_volume)

            # Add the new sound without stopping others
            sound_control.current_sounds.add(sound_file)
            sound_control.sound_objects[sound_file] = snd

            if not sound_control.paused:
                sound_control.last_play_time = time.time()
                sound_control.elapsed_time_at_pause = 0
        except pygame.error as e:
            print(f'Error playing sound: {e}')
    else:
        print('Error: Sound file not found.')

    return jsonify(sound_control.get_state_as_dict())


@app.route('/play_selected', methods=['POST'])
def play_selected() -> BaseResponse:
    files_to_play = request.form.getlist('files_to_play')
    for snd in sound_control.sound_objects.values():
        snd.stop()
    sound_control.current_sounds.clear()
    sound_control.sound_objects.clear()
    for filename in files_to_play:
        sound_path = SOUND_DIR / filename
        if sound_path.is_file():
            try:
                snd = pygame.mixer.Sound(str(sound_path))
                snd.play(loops=-1)
                sound_control.current_sounds.add(filename)
                sound_control.sound_objects[filename] = snd
            except pygame.error as e:
                print(f'Error playing sound: {e}')
    if files_to_play:
        sound_control.last_play_time = time.time()
    else:
        sound_control.last_play_time = None

    return redirect(url_for('home'))


@app.route('/stop')
def stop_sound() -> BaseResponse:
    for snd in sound_control.sound_objects.values():
        snd.stop()
    sound_control.current_sounds.clear()
    sound_control.sound_objects.clear()
    sound_control.paused = False
    sound_control.last_play_time = None
    sound_control.elapsed_time_at_pause = 0
    return jsonify(sound_control.get_state_as_dict())


@app.route('/upload_file', methods=['POST'])
def upload_file() -> BaseResponse:
    files = request.files.getlist('file')

    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = SOUND_DIR / filename
            file.save(file_path)

    return redirect(url_for('home'))


@app.route('/delete_files', methods=['POST'])
def delete_files() -> BaseResponse:
    files_to_delete = request.form.getlist('files_to_delete')
    if files_to_delete:
        favorites_set = sound_control.get_favorites()
        for filename in files_to_delete:
            file_path = SOUND_DIR / filename
            if file_path.is_file():
                try:
                    if filename in sound_control.current_sounds and filename in sound_control.sound_objects:
                        sound_control.sound_objects[filename].stop()
                        del sound_control.sound_objects[filename]
                        sound_control.current_sounds.remove(filename)
                    file_path.unlink()
                    print(f'Deleted file: {filename}')
                    if filename in favorites_set:
                        favorites_set.remove(filename)
                except OSError as e:
                    print(f'Error deleting file {filename}: {e}')
        sound_control.save_favorites(favorites_set)
    return redirect(url_for('home'))


@app.route('/toggle_favorite/<sound_file>')
def toggle_favorite(sound_file: str) -> BaseResponse:
    favorites_set = sound_control.get_favorites()
    if sound_file in favorites_set:
        favorites_set.remove(sound_file)
    else:
        favorites_set.add(sound_file)
    sound_control.save_favorites(favorites_set)
    return redirect(url_for('home'))


@app.route('/favicon.ico')
def favicon() -> BaseResponse:
    static_folder = Path(app.root_path).joinpath('static')
    return send_from_directory(str(static_folder), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


if __name__ == '__main__':
    from installation import main as install
    install()

    SOUND_DIR.mkdir(exist_ok=True)
    if not FAVORITES_FILE.is_file():
        FAVORITES_FILE.touch()

    # Load volume on startup
    sound_control.load_volume()

    app.run(host='0.0.0.0', port=5000, debug=False)  # noqa: S104 Possible binding to all interfaces
