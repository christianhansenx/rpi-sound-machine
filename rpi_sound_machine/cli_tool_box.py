"""Raspberry Pi tool box module."""
import configparser
import enum
import filecmp
import subprocess  # noqa: S404 `subprocess` module is possibly insecure
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SETTINGS_FILE = 'settings.ini'
LOCAL_SERVICE_DIRECTORY = Path(__file__).parent / 'system-service'
SERVICE_STOP_SERVICE_TIME_OUT = 15.0
TEMPORARY_MAKEFILE_SETTINGS_FILE = '/tmp/makefile_settings.mk'  # noqa: S108 Probable insecure usage of temporary file


class ServiceError(Exception):
    """Could perform service request."""


class ProcessKillError(Exception):
    """Could not kill application."""


class TmuxSessionKillError(Exception):
    """Could not kill tmux session."""


class KillSignals(enum.StrEnum):
    """Kill signals for stopping application on RPI."""

    SIGTERM = '-15'  # Terminate gracefully
    SIGINT = '-2'  # Ctrl+C
    SIGKILL = '-9'  # Force kill


def _run_command(command: str, *, check: bool = True, raise_std_error: bool = True) -> subprocess.CompletedProcess:
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


def _files_are_different(file1: Path, file2: Path) -> bool:
    """Compare two files.

    Returns:
        True if files are different or if one does not exist.

    """
    if not file2.exists():
        return True
    return not filecmp.cmp(file1, file2, shallow=False)


class Settings:
    """Class container of settings."""

    def __init__(self) -> None:
        """Read settings file.

        Raises:
            FileNotFoundError: if settings file was not found.

        """
        setting_path = Path(__file__).parent / SETTINGS_FILE
        if not Path(setting_path).exists():
            error = f'Settings file not found: {setting_path}'
            raise FileNotFoundError(error)
        settings = configparser.ConfigParser()
        settings.read(setting_path)

        for key, value in settings['settings'].items():
            setattr(self, key, value)

        start_script_name = f'{self.service_name}-start.sh'
        self.service_file_name = f'{self.service_name}.service'
        self.local_service_file = LOCAL_SERVICE_DIRECTORY / self.service_file_name
        self.local_start_script = LOCAL_SERVICE_DIRECTORY / start_script_name
        self.system_service_file = Path(f'/etc/systemd/system/{self.service_file_name}')
        self.system_start_script = Path(f'/usr/local/bin/{start_script_name}')

        self.grep_process_name = f'[p]ython3 {self.application_script}'
        self.process_name = self.grep_process_name.replace('[p]', 'p')
        self.grep_process_name = '[s]ound_machine'
        self.process_name = self.application_script

        tmux_log_path_pattern = self.tmux_log_path_pattern.format(
            session_name=self.tmux_session_name,
            timestamp=r'{timestamp}',
        )
        self.tmux_log_path_search_pattern = tmux_log_path_pattern.format(timestamp='*')
        timestamp = datetime.now(tz=ZoneInfo('UTC')).strftime('%Y%m%d-%H%M%S')
        self.tmux_log_path = tmux_log_path_pattern.format(timestamp=timestamp)


settings = Settings()


class ApplicationProcess:
    """Methods for application check end ending process."""

    def __init__(self) -> None:
        """Initialize."""
        self._proc_ids = []

    def restart_service(self) -> None:
        print(f'Restarting {settings.service_name}.service')
        self.stop_service()

        # Update system service files if local file are updated
        if _files_are_different(settings.local_start_script, settings.system_start_script):
            _run_command(f'sudo chmod +x {settings.local_start_script}')
            _run_command(f'sudo cp {settings.local_start_script} {settings.system_start_script}')
        if _files_are_different(settings.local_service_file, settings.system_service_file):
            _run_command(f'sudo cp {settings.local_service_file} {settings.system_service_file}')

        self._service_request('sudo systemctl daemon-reload')
        self._service_request(f'sudo systemctl enable {settings.service_file_name}')
        self._service_request(f'sudo systemctl start {settings.service_file_name}')

        start_time = time.monotonic()
        while True:
            if self.is_service_active(raise_exception=False):
                return
            if time.monotonic() - start_time > SERVICE_STOP_SERVICE_TIME_OUT:
                break
            time.sleep(0.5)
        result = _run_command(f'systemctl status {settings.service_file_name}')
        print(result.stdout())
        self.is_service_active(raise_exception=True)

    def stop_service(self) -> None:
        if not self.is_service_active(raise_exception=False):
            return
        _run_command(f'sudo systemctl stop {settings.service_name}.service')
        start_time = time.monotonic()
        while True:
            if not self.is_service_active(raise_exception=False):
                return
            if time.monotonic() - start_time > SERVICE_STOP_SERVICE_TIME_OUT:
                error = f'Could not stop service {settings.service_name} within {SERVICE_STOP_SERVICE_TIME_OUT:.1f}s.'
                raise RuntimeError(error)
            time.sleep(0.5)

    @staticmethod
    def remove_service() -> None:
        with suppress(subprocess.CalledProcessError):
            _run_command(f'sudo rm {settings.system_service_file}')
        _run_command('sudo systemctl daemon-reload')

    @staticmethod
    def is_service_active(*, raise_exception: bool = False) -> bool:
        """Check if service is running.

        Returns:
            True if service is active, False otherwise.

        """
        command = f'systemctl is-active {settings.service_name}'
        if raise_exception:
            result = _run_command(command)
        else:
            try:
                result = _run_command(command)
            except subprocess.CalledProcessError:
                return False
        return result.stdout.strip() == 'active'

    @staticmethod
    def _service_request(command: str) -> None:
        try:
            _run_command(command)
        except subprocess.CalledProcessError as error:
            status = _run_command(f'systemctl status {settings.service_file_name}', check=False).stdout
            exception_error = f'failed on command: {command}\n{status}'
            raise ServiceError(exception_error) from error

    @staticmethod
    def get_application_ids(*, print_message: bool = True) -> list[str]:
        """Get all ID of all running application processes.

        Returns:
            list of running process id's

        """
        result = _run_command(f'pgrep -f "{settings.grep_process_name}"', check=False)
        proc_ids = result.stdout.split('\n')
        valid_proc_ids = [pid for pid in proc_ids if pid]
        if print_message:
            if valid_proc_ids:
                print(f'Process "{settings.process_name}", running ID(s): {", ".join(valid_proc_ids)}')
            else:
                print(f'Process "{settings.process_name}" is not running.')
        return valid_proc_ids

    def stop_application(self, *, msg_no_kill: bool = True) -> None:
        """Stop application on RPI.

        Raises:
            ProcessKillError: If application could not get killed.

        """
        if not (proc_ids := self.get_application_ids(print_message=False)):
            if msg_no_kill:
                print('No running process found, nothing to kill')
            return
        self.stop_service()
        print(f'Killing process "{settings.process_name}" with PID(s): {", ".join(proc_ids)}')
        kill_error = 'unknown error'
        for kill_signal in KillSignals:
            for pid in proc_ids:
                if self._check_process_id(pid):
                    result = _run_command(f'kill {kill_signal.value} {pid}', check=False, raise_std_error=False)
                    if result.returncode != 0:
                        error = (
                            f'Failed to kill "{settings.process_name}" (PID {pid}) with {kill_signal.name}: '
                            f'{result.stderr.strip()}'
                        )
                        raise ProcessKillError(error)
                    time.sleep(0.2)
            if not (kill_error := self._wait_processed_killed(kill_signal)):
                break

        else:
            raise ProcessKillError(kill_error)
        print(f'Successfully killed "{settings.process_name}" with {kill_signal.name}')

    @staticmethod
    def _check_process_id(proc_id: str) -> bool:
        result = _run_command(f'ps -p {proc_id}', check=False)
        return result.returncode == 0

    def _wait_processed_killed(self, kill_signal: KillSignals) -> str | None:
        kill_error = None
        check_reties = 10
        while True:
            if not (proc_ids := self.get_application_ids(print_message=False)):
                break
            check_reties -= 1
            if check_reties < 0:
                kill_error = (
                    f'Failed to kill'
                    f' "{settings.process_name}" with {kill_signal.name}, PID(s) still alive: {", ".join(proc_ids)}'
                )
                print(f'{kill_error}')
                break
            time.sleep(0.2)
        return kill_error

    def start_application_in_tmux_session(self) -> None:
        print(f'Starting application "{settings.application_script}" in tmux session: {settings.tmux_session_name}')
        self.kill_tmux_session(msg_no_kill=False)
        _run_command(f'tmux new-session -d -s {settings.tmux_session_name}')
        _run_command(f'tmux pipe-pane -t {settings.tmux_session_name}:0.0 -o "cat >> {settings.tmux_log_path}"')
        _run_command(
            f'tmux send-keys -t {settings.tmux_session_name}:0.0 "uv run --no-group dev {settings.application_script}" C-m',
        )
        print(f'tmux log file: {settings.tmux_log_path}')
        print(f'TO ENTER TMUX TERMINAL: tmux attach -t {settings.tmux_session_name}')

    def kill_tmux_session(self, *, msg_no_kill: bool = True) -> None:
        if msg_no_kill:
            print(f'Killing tmux session: {settings.tmux_session_name}')
        if self.is_tmux_active(raise_exception=False):
            self.stop_application(msg_no_kill=False)
            _run_command(f'tmux kill-session -t {settings.tmux_session_name}')
        if self.is_tmux_active():
            kill_error = f'Failed to kill tmux session: {settings.tmux_session_name}'
            raise TmuxSessionKillError(kill_error)
        _run_command(f'rm -f {settings.tmux_log_path_search_pattern}', check=False, raise_std_error=True)

    @staticmethod
    def is_tmux_active(*, raise_exception: bool = False) -> bool:
        """Check if application tmux session is active.

        Returns:
            True if tmux session is active, False otherwise.

        """
        if _run_command('tmux ls', check=False, raise_std_error=False).returncode:
            return False
        command = f'tmux has-session -t {settings.tmux_session_name}'
        if raise_exception:
            result = _run_command(command)
        else:
            try:
                result = _run_command(command)
            except subprocess.CalledProcessError:
                return False
        return not result.returncode


class InstallerTools:
    """Class with tools for installation and uninstallation."""

    def __init__(self, application_process: ApplicationProcess, *, skip_apt_get_update: bool = False) -> None:
        """Initialize installer tools."""
        self.application_process = application_process
        self._skip_apt_get_update = skip_apt_get_update
        self._reboot_required = False

    def set_reboot_required(self) -> None:
        self._reboot_required = True

    def apt_get_update(self) -> None:
        """Run apt-get update if not already done."""
        if not self._skip_apt_get_update:
            print('Running apt-get update')
            _run_command('sudo apt-get update')
            self._skip_apt_get_update = True

    @staticmethod
    def is_tmux_installed() -> bool:
        """Check if tmux is installed.

        Returns:
            True if tmux is installed, False otherwise.

        """
        try:
            _run_command('which tmux', check=True)
        except subprocess.CalledProcessError:
            return False
        return True

    @staticmethod
    def is_uv_installed() -> bool:
        """Check if uv is installed.

        Returns:
            True if uv is installed, False otherwise.

        """
        try:
            _run_command('which uv', check=True)
        except subprocess.CalledProcessError:
            return False
        return True

    @staticmethod
    def is_snap_installed() -> bool:
        """Check if snap is installed.

        Returns:
            True if snap is installed, False otherwise.

        """
        try:
            _run_command('which snap', check=True)
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
