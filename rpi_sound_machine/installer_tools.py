"""Raspberry Pi installation tools."""
import filecmp
import subprocess  # noqa: S404 `subprocess` module is possibly insecure
from pathlib import Path

# Define paths
SERVICE_NAME = 'rpi-sound-machine'
START_SCRIPT_NAME = f'{SERVICE_NAME}-start.sh'

SERVICE_FILE_NAME = f'{SERVICE_NAME}.service'
LOCAL_SERVICE_DIRECTORY = Path(__file__).parent / 'system-service'
LOCAL_SERVICE_FILE = LOCAL_SERVICE_DIRECTORY / SERVICE_FILE_NAME
LOCAL_START_SCRIPT = LOCAL_SERVICE_DIRECTORY / START_SCRIPT_NAME
SYSTEM_SERVICE_FILE = Path(f'/etc/systemd/system/{SERVICE_FILE_NAME}')
SYSTEM_START_SCRIPT = Path(f'/usr/local/bin/{START_SCRIPT_NAME}')


class InstallerTools:
    """Class with tools for installation and uninstallation."""

    def __init__(self, *, skip_apt_get_update: bool = False) -> None:
        """Initialize installer tools."""
        self._skip_apt_get_update = skip_apt_get_update
        self._reboot_required = False

    def set_reboot_required(self) -> None:
        self._reboot_required = True

    def apt_get_update(self) -> None:
        """Run apt-get update if not already done."""
        if not self._skip_apt_get_update:
            print('Running apt-get update')
            self.run_command('sudo apt-get update')
            self._skip_apt_get_update = True

    @staticmethod
    def run_command(command: str, *, check: bool = True, suppress_error_prints: bool = False) -> None:
        """Run a shell command.

        Args:
            command: The command to run.
            check: Whether to raise an error on a non-zero exit code.
            suppress_error_prints: Whether to suppress error prints.

        Raises:
            subprocess.CalledProcessError: If the command fails and check is True.

        """
        try:
            # Ruff S602 = `subprocess` call with `shell=True` identified, security issue
            subprocess.run(command, shell=True, check=check, capture_output=True, text=True)  # noqa: S602
        except subprocess.CalledProcessError as e:
            if not suppress_error_prints:
                print(f'\nError running command: {command}')
                print(f'Stdout: {e.stdout}')
                print(f'Stderr: {e.stderr}')
            raise

    def is_tmux_installed(self) -> bool:
        """Check if tmux is installed.

        Returns:
            True if tmux is installed, False otherwise.

        """
        try:
            self.run_command('which tmux', check=True, suppress_error_prints=True)
        except subprocess.CalledProcessError:
            return False
        return True

    @staticmethod
    def files_are_different(file1: Path, file2: Path) -> bool:
        """Compare two files.

        Returns:
            True if files are different or if one does not exist.

        """
        if not file2.exists():
            return True
        return not filecmp.cmp(file1, file2, shallow=False)

    def is_yq_installed(self) -> bool:
        """Check if yq is installed.

        Returns:
            True if yq is installed, False otherwise.

        """
        try:
            self.run_command('which yq', check=True, suppress_error_prints=True)
        except subprocess.CalledProcessError:
            return False
        return True

    def is_uv_installed(self) -> bool:
        """Check if uv is installed.

        Returns:
            True if uv is installed, False otherwise.

        """
        try:
            self.run_command('which uv', check=True, suppress_error_prints=True)
        except subprocess.CalledProcessError:
            return False
        return True

    def is_snap_installed(self) -> bool:
        """Check if snap is installed.

        Returns:
            True if snap is installed, False otherwise.

        """
        try:
            self.run_command('which snap', check=True, suppress_error_prints=True)
        except subprocess.CalledProcessError:
            return False
        return True

    @staticmethod
    def check_install_candidates(candidates: set, installable: set) -> None:
        unknown_items = candidates - installable
        if unknown_items:
            error = f'The following items are not recognized: {" ".join(unknown_items)}'
            raise ValueError(error)
