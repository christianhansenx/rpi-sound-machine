import json
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

# Mock pygame before it's imported by the app
pygame_mock = MagicMock()
pygame_mock.mixer = MagicMock()
pygame_mock.mixer.pre_init = MagicMock()
pygame_mock.mixer.init = MagicMock()
pygame_mock.mixer.Sound = MagicMock()

@pytest.fixture(autouse=True)
def mock_pygame():
    with patch.dict('sys.modules', {'pygame': pygame_mock}):
        yield

@pytest.fixture
def app():
    # Now it's safe to import the app
    from rpi_sound_machine.sound_machine import app as flask_app
    return flask_app

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def setup_test_environment(tmp_path, monkeypatch):
    """Set up a temporary test environment."""
    sounds_dir = tmp_path / 'sounds'
    sounds_dir.mkdir()
    favorites_file = tmp_path / 'favorites.txt'
    favorites_file.touch()
    volume_file = tmp_path / 'volume.json'
    with open(volume_file, 'w') as f:
        json.dump({'volume': 0.5}, f)

    from rpi_sound_machine import sound_machine
    monkeypatch.setattr(sound_machine, 'SOUND_DIR', sounds_dir)
    monkeypatch.setattr(sound_machine, 'FAVORITES_FILE', favorites_file)
    monkeypatch.setattr(sound_machine, 'VOLUME_FILE', volume_file)

    # Reset global state before each test
    monkeypatch.setattr(sound_machine, 'current_sounds', set())
    monkeypatch.setattr(sound_machine, 'sound_objects', {})
    monkeypatch.setattr(sound_machine, 'paused', False)
    monkeypatch.setattr(sound_machine, 'last_play_time', None)
    monkeypatch.setattr(sound_machine, 'elapsed_time_at_pause', 0)
    monkeypatch.setattr(sound_machine, 'global_volume', 0.5)

    # Create a dummy sound file
    (sounds_dir / 'test.wav').touch()

    return {
        'sounds_dir': sounds_dir,
        'favorites_file': favorites_file,
        'volume_file': volume_file,
    }

def test_home_page_no_sounds(client, setup_test_environment):
    # Remove the dummy sound file
    os.remove(setup_test_environment['sounds_dir'] / 'test.wav')
    response = client.get('/')
    assert response.status_code == 200
    assert b'No sound files uploaded yet' in response.data

def test_home_page_with_sounds(client, setup_test_environment):
    response = client.get('/')
    assert response.status_code == 200
    assert b'test.wav' in response.data

def test_toggle_play(client, setup_test_environment):
    # Play a sound
    response = client.get('/toggle_play/test.wav')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'test.wav' in data['active_sounds']
    assert pygame_mock.mixer.Sound.return_value.play.called

    # Stop the sound
    response = client.get('/toggle_play/test.wav')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'test.wav' not in data['active_sounds']
    assert pygame_mock.mixer.Sound.return_value.stop.called

def test_pause_resume(client, setup_test_environment):
    client.get('/toggle_play/test.wav')

    # Pause
    response = client.get('/pause_resume_all_link')
    assert response.status_code == 200
    assert json.loads(response.data)['paused'] is True
    assert pygame_mock.mixer.pause.called

    # Resume
    response = client.get('/pause_resume_all_link')
    assert response.status_code == 200
    assert json.loads(response.data)['paused'] is False
    assert pygame_mock.mixer.unpause.called

def test_stop_all(client, setup_test_environment):
    client.get('/toggle_play/test.wav')

    response = client.get('/stop')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert not data['active_sounds']
    assert pygame_mock.mixer.Sound.return_value.stop.called

def test_upload_file(client, setup_test_environment):
    sounds_dir = setup_test_environment['sounds_dir']
    data = {
        'file[]': (BytesIO(b'some sound data'), 'new_sound.wav'),
    }
    response = client.post('/upload_file', data=data, content_type='multipart/form-data')
    assert response.status_code == 302 # Redirect
    assert (sounds_dir / 'new_sound.wav').exists()

def test_delete_file(client, setup_test_environment):
    sounds_dir = setup_test_environment['sounds_dir']
    assert (sounds_dir / 'test.wav').exists()

    response = client.post('/delete_files', data={'files_to_delete': 'test.wav'})
    assert response.status_code == 302 # Redirect
    assert not (sounds_dir / 'test.wav').exists()

def test_toggle_favorite(client, setup_test_environment):
    favorites_file = setup_test_environment['favorites_file']

    # Add to favorites
    response = client.get('/toggle_favorite/test.wav')
    assert response.status_code == 302 # Redirect
    with open(favorites_file) as f:
        assert 'test.wav' in f.read()

    # Remove from favorites
    response = client.get('/toggle_favorite/test.wav')
    assert response.status_code == 302 # Redirect
    with open(favorites_file) as f:
        assert 'test.wav' not in f.read()

def test_set_volume(client, setup_test_environment, mocker):
    # Mock the schedule_volume_save function to prevent file writing
    mocker.patch('rpi_sound_machine.sound_machine.schedule_volume_save')

    volume_file = setup_test_environment['volume_file']
    client.get('/toggle_play/test.wav')

    response = client.get('/set_volume/0.8')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['volume'] == 0.8
    pygame_mock.mixer.Sound.return_value.set_volume.assert_called_with(0.8)

    # The volume saving is on a timer, so we can't easily test the file write
    # without more complex mocking of the Timer.
    # We will trust the set_volume function sets the global var correctly.
    from rpi_sound_machine import sound_machine
    assert sound_machine.global_volume == 0.8
