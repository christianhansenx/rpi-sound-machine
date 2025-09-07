"""Raspberry Pi installation script."""
import filecmp
import subprocess  # noqa: S404 `subprocess` module is possibly insecure
from pathlib import Path

# Define paths
SERVICE_NAME = 'rpi-sound-machine'
SERVICE_FILE_NAME = f'{SERVICE_NAME}.service'
START_SCRIPT_NAME = f'start-{SERVICE_NAME}.sh'

LOCAL_SERVICE_DIRECTORY = Path(__file__).parent / 'system-service'
LOCAL_SERVICE_FILE = LOCAL_SERVICE_DIRECTORY / SERVICE_FILE_NAME
LOCAL_START_SCRIPT = LOCAL_SERVICE_DIRECTORY / START_SCRIPT_NAME
REMOTE_SERVICE_FILE = Path(f'/etc/systemd/system/{SERVICE_FILE_NAME}')
REMOTE_START_SCRIPT = Path(f'/usr/local/bin/{START_SCRIPT_NAME}')


def run_command(command: str, *, check: bool = True) -> None:
    """Run a shell command.

    Args:
        command: The command to run.
        check: Whether to raise an error on a non-zero exit code.

    Raises:
        subprocess.CalledProcessError: If the command fails and check is True.

    """
    try:
        # Ruff S602 = `subprocess` call with `shell=True` identified, security issue
        result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True)  # noqa: S602

        if result.stderr:
            print(f'Running command: {command}')
            print(result.stdout)
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f'\nError running command: {command}')
        print(f'Stdout: {e.stdout}')
        print(f'Stderr: {e.stderr}')
        raise


def is_tmux_installed() -> bool:
    """Check if tmux is installed.

    Returns:
        True if tmux is installed, False otherwise.

    """
    try:
        run_command('which tmux', check=True)
    except subprocess.CalledProcessError:
        return False
    return True


def install_tmux() -> None:
    """Install tmux."""
    if not is_tmux_installed():
        print('tmux not found. Installing...')
        run_command('sudo apt-get update')
        run_command('sudo apt-get install -y tmux')
        print('tmux installed successfully.')


def files_are_different(file1: Path, file2: Path) -> bool:
    """Compare two files.

    Returns:
        True if files are different or if one does not exist.

    """
    if not file2.exists():
        return True
    return not filecmp.cmp(file1, file2, shallow=False)


def install_service() -> None:
    """Install the systemd service."""
    service_changed = files_are_different(LOCAL_SERVICE_FILE, REMOTE_SERVICE_FILE)
    script_changed = files_are_different(LOCAL_START_SCRIPT, REMOTE_START_SCRIPT)

    if not service_changed and not script_changed:
        print('Service and start script are up to date. No changes needed.')
        return

    print('Changes detected, installing/updating service.')

    # Stop the service before making changes
    run_command(f'sudo systemctl stop {SERVICE_NAME}', check=False)

    if service_changed:
        print('Service file is different. Updating...')
        run_command(f'sudo cp {LOCAL_SERVICE_FILE} {REMOTE_SERVICE_FILE}')
        print('Service file updated.')

    if script_changed:
        print('Start script is different. Updating...')
        run_command(f'sudo cp {LOCAL_START_SCRIPT} {REMOTE_START_SCRIPT}')
        run_command(f'sudo chmod +x {REMOTE_START_SCRIPT}')
        print('Start script updated.')

    # print('Reloading systemd daemon and restarting service.')
    # run_command('sudo systemctl daemon-reload')
    # run_command(f'sudo systemctl enable {SERVICE_NAME}')
    # run_command(f'sudo systemctl start {SERVICE_NAME}')
    # print('Service installation/update complete.')


def is_uv_installed() -> bool:
    """Check if uv is installed.

    Returns:
        True if uv is installed, False otherwise.

    """
    try:
        run_command('which uv', check=True)
    except subprocess.CalledProcessError:
        return False
    return True


def install_uv() -> None:
    """Install uv."""
    if not is_uv_installed():
        print('uv not found. Installing...')
        run_command('curl -LsSf https://astral.sh/uv/install.sh | sh')
        print('uv installed successfully.')
    else:
        print('uv is already installed.')


def rpi_installation() -> None:
    """Install RPI."""
    install_tmux()
    # install_uv()
    install_service()
