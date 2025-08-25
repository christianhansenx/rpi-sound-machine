"""Unit tests for the sound machine application."""
import json
from collections.abc import Generator
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

# Mock pygame before it's imported by the app
pygame_mock = MagicMock()
pygame_mock.mixer = MagicMock()
pygame_mock.mixer.pre_init = MagicMock()
pygame_mock.mixer.init = MagicMock()
pygame_mock.mixer.Sound = MagicMock()

TEST_VOLUME = 0.8


@pytest.fixture(autouse=True)
def mock_pygame() -> Generator[None, Any]:
    """Mock the pygame library."""
    with patch.dict('sys.modules', {'pygame': pygame_mock}):
        yield


@pytest.fixture
def app() -> Flask:
    """Fixture for the Flask app."""
    # Now it's safe to import the app (qa PLC0415 `import` should be at the top-level of a file)
    from rpi_sound_machine.sound_machine import app as flask_app  # noqa: PLC0415
    return flask_app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Provide a test client for the app."""
    return app.test_client()


@pytest.fixture
def setup_test_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Set up a temporary test environment."""
    from rpi_sound_machine import sound_machine  # noqa: PLC0415 `import` should be at the top-level of a file
    sounds_dir = tmp_path / 'sounds'
    sounds_dir.mkdir()
    favorites_file = tmp_path / 'favorites.txt'
    favorites_file.touch()
    volume_file = tmp_path / 'volume.json'
    with volume_file.open('w') as f:
        json.dump({'volume': 0.5}, f)

    monkeypatch.setattr(sound_machine, 'SOUND_DIR', sounds_dir)
    monkeypatch.setattr(sound_machine, 'FAVORITES_FILE', favorites_file)
    monkeypatch.setattr(sound_machine, 'VOLUME_FILE', volume_file)

    monkeypatch.setattr(sound_machine.sound_control, 'global_volume', 0.5)
    monkeypatch.setattr(sound_machine.sound_control, 'paused', False)
    monkeypatch.setattr(sound_machine.sound_control, 'current_sounds', set())
    monkeypatch.setattr(sound_machine.sound_control, 'elapsed_time_at_pause', 0)
    monkeypatch.setattr(sound_machine.sound_control, 'last_play_time', None)
    monkeypatch.setattr(sound_machine.sound_control, 'sound_objects', {})

    # Create a dummy sound file
    (sounds_dir / 'test.wav').touch()

    return {
        'sounds_dir': sounds_dir,
        'favorites_file': favorites_file,
        'volume_file': volume_file,
        'sound_machine': sound_machine,
    }


def test_home_page_no_sounds(client: FlaskClient, setup_test_environment: dict[str, Any]) -> None:
    """Test the home page when no sounds are present."""
    # Remove the dummy sound file
    (setup_test_environment['sounds_dir'] / 'test.wav').unlink()
    response = client.get('/')
    assert response.status_code == HTTPStatus.OK
    assert b'No sound files uploaded yet' in response.data


def test_home_page_with_sounds(client: FlaskClient, setup_test_environment: dict[str, Any]) -> None:
    """Test the home page when sounds are present."""
    del(setup_test_environment)  # Avoid qa ARG001 Unused function argument
    response = client.get('/')
    assert response.status_code == HTTPStatus.OK
    assert b'test.wav' in response.data


def test_toggle_play(client: FlaskClient, setup_test_environment: dict[str, Any]) -> None:
    """Test toggling play and stop for a sound."""
    del(setup_test_environment)  # Avoid qa ARG001 Unused function argument

    # Play a sound
    response = client.get('/toggle_play/test.wav')
    assert response.status_code == HTTPStatus.OK
    data = json.loads(response.data)
    assert 'test.wav' in data['active_sounds']
    assert pygame_mock.mixer.Sound.return_value.play.called

    # Stop the sound
    response = client.get('/toggle_play/test.wav')
    assert response.status_code == HTTPStatus.OK
    data = json.loads(response.data)
    assert 'test.wav' not in data['active_sounds']
    assert pygame_mock.mixer.Sound.return_value.stop.called


def test_pause_resume(client: FlaskClient, setup_test_environment: dict[str, Any]) -> None:
    """Test pausing and resuming all sounds."""
    del(setup_test_environment)  # Avoid qa ARG001 Unused function argument
    client.get('/toggle_play/test.wav')

    # Pause
    response = client.get('/pause_resume_all_link')
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.data)['paused'] is True
    assert pygame_mock.mixer.pause.called

    # Resume
    response = client.get('/pause_resume_all_link')
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.data)['paused'] is False
    assert pygame_mock.mixer.unpause.called


def test_stop_all(client: FlaskClient, setup_test_environment: dict[str, Any]) -> None:
    """Test stopping all sounds."""
    del(setup_test_environment)  # Avoid qa ARG001 Unused function argument
    client.get('/toggle_play/test.wav')

    response = client.get('/stop')
    assert response.status_code == HTTPStatus.OK
    data = json.loads(response.data)
    assert not data['active_sounds']
    assert pygame_mock.mixer.Sound.return_value.stop.called


def test_upload_file(client: FlaskClient, setup_test_environment: dict[str, Any]) -> None:
    """Test uploading a file."""
    sounds_dir = setup_test_environment['sounds_dir']
    data = {
        'file': (BytesIO(b'some sound data'), 'new_sound.wav'),
    }
    response = client.post('/upload_file', data=data, content_type='multipart/form-data')
    assert response.status_code == HTTPStatus.FOUND
    assert (sounds_dir / 'new_sound.wav').exists()


def test_delete_file(client: FlaskClient, setup_test_environment: dict[str, Any]) -> None:
    """Test deleting a file."""
    sounds_dir = setup_test_environment['sounds_dir']
    assert (sounds_dir / 'test.wav').exists()

    response = client.post('/delete_files', data={'files_to_delete': 'test.wav'})
    assert response.status_code == HTTPStatus.FOUND
    assert not (sounds_dir / 'test.wav').exists()


def test_toggle_favorite(client: FlaskClient, setup_test_environment: dict[str, Any]) -> None:
    """Test toggling a favorite."""
    favorites_file = setup_test_environment['favorites_file']

    # Add to favorites
    response = client.get('/toggle_favorite/test.wav')
    assert response.status_code == HTTPStatus.FOUND
    with favorites_file.open() as f:
        assert 'test.wav' in f.read()

    # Remove from favorites
    response = client.get('/toggle_favorite/test.wav')
    assert response.status_code == HTTPStatus.FOUND
    with favorites_file.open() as f:
        assert 'test.wav' not in f.read()


def test_set_volume(client: FlaskClient, setup_test_environment: dict[str, Any], mocker: MagicMock) -> None:
    """Test setting the volume."""
    sound_machine = setup_test_environment['sound_machine']
    # Mock the schedule_volume_save function to prevent file writing
    mocker.patch('rpi_sound_machine.sound_machine.sound_control.schedule_volume_save')

    client.get('/toggle_play/test.wav')

    response = client.get(f'/set_volume/{TEST_VOLUME}')
    assert response.status_code == HTTPStatus.OK
    data = json.loads(response.data)
    assert data['volume'] == TEST_VOLUME
    pygame_mock.mixer.Sound.return_value.set_volume.assert_called_with(TEST_VOLUME)

    # The volume saving is on a timer, so we can't easily test the file write
    # without more complex mocking of the Timer.
    # We will trust the set_volume function sets the global var correctly.
    assert sound_machine.sound_control.global_volume == TEST_VOLUME
