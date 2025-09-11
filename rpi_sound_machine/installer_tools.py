"""Raspberry Pi installation tools."""
import filecmp
import subprocess  # noqa: S404 `subprocess` module is possibly insecure
import time
from pathlib import Path

# Define paths
SERVICE_NAME = 'rpi-sound-machine'
START_SCRIPT_NAME = f'{SERVICE_NAME}-start.sh'

SERVICE_STOP_SERVICE_TIME_OUT = 15.0
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
    def run_command(
            command: str,
            *,
            check: bool = True,
            raise_std_error: bool = True,
    ) -> subprocess.CompletedProcess:
        r"""Run a shell command.

        Args:
            command: The command to run.
            check: Whether to raise an error on a non-zero exit code.
            raise_std_error: Whether to raise an error if there is output on stderr.

        Returns:
            The CompletedProcess instance.
            Example: CompletedProcess(args='sudo snap remove yq', returncode=0, stdout='', stderr='snap "yq" is not installed\n')

        Raises:
            subprocess.CalledProcessError: If the command fails and check is True, or .

        """
        # Ruff S602 = `subprocess` call with `shell=True` identified, security issue
        result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True)  # noqa: S602
        if raise_std_error and result.stderr:
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result

    def restart_service(self) -> None:
        print(f'Restarting {SERVICE_NAME}.service')
        self.stop_service()

        if self.files_are_different(LOCAL_SERVICE_FILE, SYSTEM_SERVICE_FILE):
            self.run_command(f'sudo cp {LOCAL_SERVICE_FILE} {SYSTEM_SERVICE_FILE}')
        if self.files_are_different(LOCAL_START_SCRIPT, SYSTEM_START_SCRIPT):
            self.run_command(f'sudo cp {LOCAL_START_SCRIPT} {SYSTEM_START_SCRIPT}')
            self.run_command(f'sudo chmod +x {SYSTEM_START_SCRIPT}')

        self.run_command('sudo systemctl daemon-reload')
        self.run_command(f'sudo systemctl enable {SERVICE_NAME}.service')
        self.run_command(f'sudo systemctl start {SERVICE_NAME}.service')

        start_time = time.monotonic()
        while True:
            if self.is_service_active(raise_exception=False):
                return
            if time.monotonic() - start_time > SERVICE_STOP_SERVICE_TIME_OUT:
                break
            time.sleep(0.5)
        self.is_service_active(raise_exception=True)

    def stop_service(self) -> None:
        if not self.is_service_active(raise_exception=False):
            return
        self.run_command(f'sudo systemctl stop {SERVICE_NAME}.service')
        start_time = time.monotonic()
        while True:
            if not self.is_service_active(raise_exception=False):
                return
            if time.monotonic() - start_time > SERVICE_STOP_SERVICE_TIME_OUT:
                error = f'Could not stop service {SERVICE_NAME} within {SERVICE_STOP_SERVICE_TIME_OUT:.1f}s.'
                raise RuntimeError(error)
            time.sleep(0.5)

    def is_service_active(self, *, raise_exception: bool = False) -> bool:
        """Check if service is running.

        Returns:
            True if service is active, False otherwise.

        """
        command = f'systemctl is-active {SERVICE_NAME}'
        if raise_exception:
            result = self.run_command(command, check=True)
        else:
            try:
                result = self.run_command(command, check=True)
            except subprocess.CalledProcessError:
                return False
        return result.stdout.strip() == 'active'

    def is_tmux_installed(self) -> bool:
        """Check if tmux is installed.

        Returns:
            True if tmux is installed, False otherwise.

        """
        try:
            self.run_command('which tmux', check=True)
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
            self.run_command('which yq', check=True)
        except subprocess.CalledProcessError:
            return False
        return True

    def is_uv_installed(self) -> bool:
        """Check if uv is installed.

        Returns:
            True if uv is installed, False otherwise.

        """
        try:
            self.run_command('which uv', check=True)
        except subprocess.CalledProcessError:
            return False
        return True

    def is_snap_installed(self) -> bool:
        """Check if snap is installed.

        Returns:
            True if snap is installed, False otherwise.

        """
        try:
            self.run_command('which snap', check=True)
        except subprocess.CalledProcessError:
            return False
        return True

    @staticmethod
    def check_install_candidates(installable: list, candidates: list) -> list:
        unknown_items = set(candidates) - set(installable)
        if unknown_items:
            error = f'The following items are not recognized: {" ".join(unknown_items)}'
            raise ValueError(error)
        return [item for item in installable if item in candidates]
