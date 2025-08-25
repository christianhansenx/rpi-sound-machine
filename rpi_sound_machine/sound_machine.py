"""Raspberry Pi Sound Machine - A web-based sound machine using Flask and Pygame."""
import json
import time
from pathlib import Path
from threading import Timer

import pygame
from flask import Flask, jsonify, redirect, render_template_string, request, send_from_directory, url_for
from werkzeug.utils import secure_filename
from werkzeug.wrappers import Response as BaseResponse

# Initialize Flask app
app = Flask(__name__)

# Initialize Pygame mixer
pygame.mixer.pre_init(44100, -16, 2, 4096)
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
        """Return the current state of the SoundControl as a JSON-serializable dictionary."""
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


HOME_PAGE_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Raspberry Pi Sound Machine</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/x-icon" href="{{ url_for('static', filename='favicon.ico') }}">
    <link rel="shortcut icon" type="image/x-icon" href="{{ url_for('static', filename='favicon.ico') }}">
    <style>
        * {
            -webkit-tap-highlight-color: transparent !important;
            -webkit-touch-callout: none !important;
        }
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; background-color: #f0f0f0; }
        .container {
            max-width: 600px;
            margin: auto;
            padding: 20px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            text-align: left;
        }
        h1 { color: #333; text-align: center; font-size: 24px; }
        h2 { color: #333; text-align: center; font-size: 20px; margin-top: 30px; }
        hr { border: 0; border-top: 1px solid #ccc; margin: 20px 0; }

        .list-section {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 10px;
            margin-top: 10px;
        }
        .file-list { list-style: none; padding: 0; margin: 0; }
        .file-list-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px;
            border-bottom: 1px solid #eee;
        }
        .file-list-item:last-child { border-bottom: none; }
        .file-list-item:hover { background-color: #f9f9f9; }

        .file-name-link {
            flex-grow: 1;
            padding: 0;
            text-decoration: none;
            color: #333;
            font-size: 16px;
            line-height: 1.2;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .file-name-link.active-sound { font-weight: bold; color: #28a745; }
        .file-name-link.active-sound:hover { color: #218838; }

        .icon-group {
            display: flex;
            align-items: center;
            flex-shrink: 0;
        }
        .favorite-toggle {
            background: none;
            border: none;
            font-size: 20px;
            cursor: pointer;
            padding: 0 10px;
            text-decoration: none;
        }
        .delete-checkbox {
            transform: scale(1.2);
            margin-left: 10px;
        }

        .action-buttons {
            display: flex;
            justify-content: center;
            align-items: center;
            margin-top: 20px;
            margin-bottom: 20px;
            gap: 20px;
        }
        .action-button,
        .action-button:visited,
        .action-button:active,
        .action-button:focus {
            width: 60px;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
            border-radius: 50%;
            font-size: 48px;
            color: #333 !important;
            cursor: pointer;
            margin: 0 5px;
            text-decoration: none !important;
            appearance: none !important;
            -webkit-appearance: none !important;
            -moz-appearance: none !important;
        }
        .action-button:hover {
            background-color: #f5f5f5 !important;
        }

        /* New CSS rule to make the stop/pause buttons blue */
        .action-button.stop-button,
        .action-button.stop-button:visited,
        .action-button.stop-button:active,
        .action-button.stop-button:focus {
            color: #007BFF !important;
            background: transparent !important;
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
        }

        #play-timer {
            font-size: 18px;
            font-weight: bold;
            color: #555;
            min-width: 50px;
            text-align: center;
            margin-top: 10px;
        }

        .volume-control-container {
            display: flex;
            align-items: center;
            justify-content: center;
            margin-top: 20px;
        }
        #volume-slider {
            width: 200px;
            margin: 0 10px;
        }
        .volume-label {
            font-size: 16px;
            color: #555;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵 Raspberry Pi Sound Machine</h1>

        <form action="/delete_files" method="post">
            <div class="action-buttons">
                <a href="#" id="pause-resume-btn" class="action-button stop-button" title="Pause/Resume All">
                    {% if sound_state.paused %}
                        ▶️
                    {% else %}
                        ⏸️
                    {% endif %}
                </a>
                <a href="#" id="stop-btn" class="action-button stop-button" title="Stop All">⏹️</a>
                <button type="submit" class="action-button delete-button" title="Delete Selected">🗑️</button>
            </div>
            <div id="play-timer">00:00:00</div>

            <div class="volume-control-container">
                <span class="volume-label">🔊</span>
                <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value="{{ sound_state.volume }}"
                    id="volume-slider"
                    title="Volume Control"
                >
            </div>

            <div class="list-section">
                {% if sound_files %}
                    <ul class="file-list">
                        {% for sound_file in sound_files %}
                        <li class="file-list-item">
                            <a href="#"
                                class="file-name-link"
                                data-file-name="{{ sound_file }}"
                            >
                                {{ sound_file }}
                            </a>
                            <div class="icon-group">
                                <a href="/toggle_favorite/{{ sound_file }}" class="favorite-toggle">🤍</a>
                                <input type="checkbox" name="files_to_delete" value="{{ sound_file }}" class="delete-checkbox">
                            </div>
                        </li>
                        {% endfor %}
                    </ul>
                {% else %}
                    <p>No sound files uploaded yet.</p>
                {% endif %}
            </div>

            <h2>Favorites</h2>
            <div class="list-section">
                {% if favorites %}
                    <ul class="file-list">
                        {% for sound_file in favorites %}
                        <li class="file-list-item">
                            <a href="#" class="file-name-link"
                                data-file-name="{{ sound_file }}"
                            >
                                {{ sound_file }}
                            </a>
                            <div class="icon-group">
                                <a href="/toggle_favorite/{{ sound_file }}" class="favorite-toggle">❤️</a>
                            </div>
                        </li>
                        {% endfor %}
                    </ul>
                {% else %}
                    <p>No favorite sounds yet.</p>
                {% endif %}
            </div>
        </form>

        <div class="upload-form">
            <h2>Upload Sound Files</h2>
            <form action="/upload_file" method="post" enctype="multipart/form-data">
                <div class="upload-input-group">
                    <input type="file" name="file" multiple class="file-input">
                    <input type="submit" value="Upload" class="upload-button">
                </div>
            </form>
        </div>
    </div>

    <script>
        const playTimer = document.getElementById('play-timer');
        const pauseResumeBtn = document.getElementById('pause-resume-btn');
        const stopBtn = document.getElementById('stop-btn');
        const fileLinks = document.querySelectorAll('.file-name-link');
        const volumeSlider = document.getElementById('volume-slider');

        let lastPlayTime = {{ sound_state.last_play_time if sound_state.last_play_time is not none else 'null' }};
        let elapsedAtPause = {{ sound_state.elapsed_time_at_pause }};
        let timerInterval = null;

        // Function to update the active sound class based on server state
        function updateActiveSounds(activeSounds) {
            fileLinks.forEach(link => {
                const fileName = link.dataset.fileName;
                if (activeSounds.includes(fileName)) {
                    link.classList.add('active-sound');
                } else {
                    link.classList.remove('active-sound');
                }
            });
        }

        // Initial setup from server-side rendered data
        updateActiveSounds({{ sound_state.active_sounds | tojson }});

        function updateTimer() {
            let totalElapsedSeconds = elapsedAtPause;
            if (lastPlayTime) {
                const now = Date.now() / 1000;
                totalElapsedSeconds = Math.floor(now - lastPlayTime + elapsedAtPause);
            }

            if (totalElapsedSeconds >= 0) {
                const hours = Math.floor(totalElapsedSeconds / 3600);
                const minutes = Math.floor((totalElapsedSeconds % 3600) / 60);
                const seconds = totalElapsedSeconds % 60;

                const formattedHours = String(hours).padStart(2, '0');
                const formattedMinutes = String(minutes).padStart(2, '0');
                const formattedSeconds = String(seconds).padStart(2, '0');

                playTimer.textContent = formattedHours + ':' + formattedMinutes + ':' + formattedSeconds;
            } else {
                playTimer.textContent = '00:00:00';
            }
        }

        function startTimer() {
            if (!timerInterval) {
                timerInterval = setInterval(updateTimer, 1000);
            }
        }

        function pauseTimer() {
            clearInterval(timerInterval);
            timerInterval = null;
        }

        function stopTimer() {
            clearInterval(timerInterval);
            timerInterval = null;
            playTimer.textContent = '00:00:00';
        }

        // Initial timer setup
        if (lastPlayTime) {
            startTimer();
        } else {
            stopTimer();
        }

        // Asynchronous handling of sound playback

        // Sound file links
        fileLinks.forEach(link => {
            link.addEventListener('click', async (e) => {
                e.preventDefault();
                const fileName = e.target.dataset.fileName;
                const response = await fetch(`/toggle_play/${fileName}`);
                const data = await response.json();

                // Update UI based on response
                lastPlayTime = data.last_play_time;
                elapsedAtPause = data.elapsed_time_at_pause;

                // Update timer
                if (lastPlayTime) {
                    startTimer();
                } else {
                    stopTimer();
                }

                // Update active sound class for all links
                updateActiveSounds(data.active_sounds);
            });
        });

        // Pause/Resume button
        pauseResumeBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            const response = await fetch('/pause_resume_all_link');
            const data = await response.json();

            // Update UI based on response
            lastPlayTime = data.last_play_time;
            elapsedAtPause = data.elapsed_time_at_pause;

            if (data.paused) {
                pauseResumeBtn.innerHTML = '▶️';
                pauseTimer(); // Only pauses the countdown
            } else {
                pauseResumeBtn.innerHTML = '⏸️';
                startTimer();
            }
            updateActiveSounds(data.active_sounds);
        });

        // Stop button
        stopBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            const response = await fetch('/stop');
            const data = await response.json();

            // Update UI based on response
            lastPlayTime = data.last_play_time;
            elapsedAtPause = data.elapsed_time_at_pause;

            pauseResumeBtn.innerHTML = '⏸️';
            stopTimer(); // Resets the timer to 00:00:00
            updateActiveSounds(data.active_sounds);
        });

        // Volume slider
        volumeSlider.addEventListener('input', async (e) => {
            const newVolume = e.target.value;
            await fetch(`/set_volume/${newVolume}`);
        });
    </script>
</body>
</html>
"""


@app.route('/')
def home() -> BaseResponse:
    all_files = [f.name for f in SOUND_DIR.glob('*') if f.is_file()]
    favorites_set = sound_control.get_favorites()

    # Separate the files into favorites and non-favorites
    favorite_files = sorted([f for f in all_files if f in favorites_set])
    non_favorite_files = sorted([f for f in all_files if f not in favorites_set])

    sound_state = sound_control.get_state_as_dict()

    return render_template_string(
        HOME_PAGE_TEMPLATE,
        sound_state=sound_state,
        sound_files=non_favorite_files,
        favorites=favorite_files,
    )


@app.route('/pause_resume_all_link')
def pause_resume_all_link() -> BaseResponse:
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


@app.route('/pause_resume_all', methods=['POST'])
def pause_resume_all() -> BaseResponse:
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
        if file and file.filename != '':
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
    SOUND_DIR.mkdir(exist_ok=True)
    if not FAVORITES_FILE.is_file():
        FAVORITES_FILE.touch()

    # Load volume on startup
    sound_control.load_volume()

    app.run(host='0.0.0.0', port=5000, debug=False)  # noqa: S104 Possible binding to all interfaces
