"""Raspberry Pi tool box module."""
import configparser
import filecmp
import subprocess  # noqa: S404 `subprocess` module is possibly insecure
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SETTINGS_FILE = 'settings.ini'
SETTINGS_APPLICATION_KEYWORD = 'application'
SETTINGS_TMUX_KEYWORD = 'tmux'
LOCAL_SERVICE_DIRECTORY = Path(__file__).parent / 'system-service'
SERVICE_STOP_SERVICE_TIME_OUT = 15.0
TEMPORARY_MAKEFILE_SETTINGS_FILE = '/tmp/makefile_settings.mk'  # noqa: S108 Probable insecure usage of temporary file


class Settings:
    """Class container of settings."""

    def __init__(self) -> None:
        """Read settings file.

        Raises:
            FileNotFoundError: if settings file was not found.

        """
        if not Path(SETTINGS_FILE).exists():
            error = f'Settings file not found: {SETTINGS_FILE}'
            raise FileNotFoundError(error)
        self._settings_data = configparser.ConfigParser()
        self._settings_data.read(SETTINGS_FILE)

        self.service_name = self._settings_data[SETTINGS_APPLICATION_KEYWORD]['service_name']
        start_script_name = f'{self.service_name}-start.sh'
        service_file_name = f'{self.service_name}.service'
        self.local_service_file = LOCAL_SERVICE_DIRECTORY / service_file_name
        self.local_start_script = LOCAL_SERVICE_DIRECTORY / start_script_name
        self.system_service_file = Path(f'/etc/systemd/system/{service_file_name}')
        self.system_start_script = Path(f'/usr/local/bin/{start_script_name}')

    def create_make_include_file(self) -> None:
        tmux_session_name = self._settings_data[SETTINGS_TMUX_KEYWORD]['session_name']
        tmux_file_path_pattern = self._settings_data[SETTINGS_TMUX_KEYWORD]['log_file_path_pattern'].format(
            session_name=tmux_session_name,
            timestamp=r'{timestamp}',
        )
        tmux_log_file_time_stamp = datetime.now(tz=ZoneInfo('UTC')).strftime('%Y%m%d_%H%M%S')

        mk_file = Path(TEMPORARY_MAKEFILE_SETTINGS_FILE)
        mk_file.write_text(
            '\n'.join([
                f'APPLICATION_SCRIPT := "{self._settings_data[SETTINGS_APPLICATION_KEYWORD]["script"]}"',
                f'TMUX_SESSION_NAME := "{tmux_session_name}"',
                f'TMUX_LOG_FILES_TO_REMOVE := "{tmux_file_path_pattern.format(timestamp="*")}"',
                f'TMUX_LOG_FILE := "{tmux_file_path_pattern.format(timestamp=tmux_log_file_time_stamp)}"',
            ]) + '\n',
            encoding='utf-8',
        )


settings = Settings()


class InstallerTools:
    """Class with tools for installation and uninstallation."""

    def __init__(self, *, skip_apt_get_update: bool = False) -> None:
        """Initialize installer tools."""
        self._skip_apt_get_update = skip_apt_get_update
        self._reboot_required = False

        # Update service files if updated
        if self.files_are_different(settings.local_start_script, settings.system_start_script):
            self.run_command(f'sudo chmod +x {settings.local_start_script}')
            self.run_command(f'sudo cp {settings.local_start_script} {settings.system_start_script}')
        if self.files_are_different(settings.local_service_file, settings.system_service_file):
            self.run_command(f'sudo cp {settings.local_service_file} {settings.system_service_file}')

    def set_reboot_required(self) -> None:
        self._reboot_required = True

    def apt_get_update(self) -> None:
        """Run apt-get update if not already done."""
        if not self._skip_apt_get_update:
            print('Running apt-get update')
            self.run_command('sudo apt-get update')
            self._skip_apt_get_update = True

    def get_process_ids(self, process_name: str, *, message_no_process: bool = True) -> list[str]:
        """Check about processes are running.

        Returns:
            list of running process id's

        """
        _stdin, stdout, _stderr = ssh_client.client.exec_command(f'pgrep -f "{process_name}"')
        proc_ids = stdout.read().decode('utf-8').strip().split('\n')
        return [pid for pid in proc_ids if pid]


        proc_ids = _rpi_check_running_app(ssh_client, process_name)
        valid_proc_ids = [pid for pid in proc_ids if pid]
        if valid_proc_ids:
            print(f'Process "{process_name}" running')
            print(f'Found existing PID(s): {", ".join(valid_proc_ids)}')
        elif message_no_process:
            print(f'No existing process found of "{ssh_client.connection} {process_name}"')
        return valid_proc_ids

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
        print(f'Restarting {settings.service_name}.service')
        self.stop_service()

        self.run_command('sudo systemctl daemon-reload')
        self.run_command(f'sudo systemctl enable {settings.service_name}.service')
        self.run_command(f'sudo systemctl start {settings.service_name}.service')

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
        self.run_command(f'sudo systemctl stop {settings.service_name}.service')
        start_time = time.monotonic()
        while True:
            if not self.is_service_active(raise_exception=False):
                return
            if time.monotonic() - start_time > SERVICE_STOP_SERVICE_TIME_OUT:
                error = f'Could not stop service {settings.service_name} within {SERVICE_STOP_SERVICE_TIME_OUT:.1f}s.'
                raise RuntimeError(error)
            time.sleep(0.5)

    def remove_service(self) -> None:
        with suppress(subprocess.CalledProcessError):
            self.run_command(f'sudo rm {settings.system_service_file}')
        self.run_command('sudo systemctl daemon-reload')

    def is_service_active(self, *, raise_exception: bool = False) -> bool:
        """Check if service is running.

        Returns:
            True if service is active, False otherwise.

        """
        command = f'systemctl is-active {settings.service_name}'
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
