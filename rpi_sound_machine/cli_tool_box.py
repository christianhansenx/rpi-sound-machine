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


class ServiceStatus(enum.StrEnum):
    """Status of service for application on RPI."""

    ACTIVE = 'running'
    ENABLED_INACTIVE = 'enabled (inactive)'
    INACTIVE = 'inactive'
    NOT_FOUND = 'not found'


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
        self.system_service_file_path = Path(f'/etc/systemd/system/{self.service_file_name}')
        self.system_start_script_path = Path(f'/usr/local/bin/{start_script_name}')

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

    @staticmethod
    def get_service_status() -> tuple[ServiceStatus, str]:
        def _get_status_value(systemctl_status: subprocess.CompletedProcess) -> ServiceStatus:
            if systemctl_status.returncode == 0:
                return ServiceStatus.ACTIVE
            if 'service; enabled' in systemctl_status.stdout:
                return ServiceStatus.ENABLED_INACTIVE
            if 'could not be found' in systemctl_status.stderr:
                return ServiceStatus.NOT_FOUND
            return ServiceStatus.INACTIVE

        result = _run_command(f'TZ=UTC systemctl status {settings.service_file_name}', check=False, raise_std_error=False)
        status = _get_status_value(result)
        return status, result.stdout

    def wait_service_status(self, expected_status: ServiceStatus, timeout: float = 5) -> None:
        start_time = time.monotonic()
        while True:
            status, status_log = self.get_service_status()
            if status == expected_status:
                return
            if time.monotonic() > start_time + timeout:
                error = f'Unexpected service status. Expected: {expected_status}, Actual: {status}\n{status_log}'
                raise ServiceError(error)
            time.sleep(0.5)

    def restart_service(self) -> None:
        print(f'Restarting {settings.service_name}.service')
        self.stop_application(msg_no_kill=False)
        self.kill_tmux_session()
        self.remove_service(show_no_service_to_remove_msg=False)
        self.start_service()

    def start_service(self, *, show_start_msg: bool = True) -> None:
        if show_start_msg:
            print(f'Starting service {settings.service_file_name}')
        if _files_are_different(settings.local_start_script, settings.system_start_script_path):
            _run_command(f'sudo chmod +x {settings.local_start_script}')
            _run_command(f'sudo cp {settings.local_start_script} {settings.system_start_script_path}')
        if _files_are_different(settings.local_service_file, settings.system_service_file_path):
            _run_command(f'sudo cp {settings.local_service_file} {settings.system_service_file_path}')

        _run_command(f'sudo systemctl enable {settings.service_file_name}', check=False, raise_std_error=False)
        self.wait_service_status(ServiceStatus.ENABLED_INACTIVE)
        _run_command(f'sudo systemctl start {settings.service_file_name}')
        _run_command('sudo systemctl daemon-reload')
        self.wait_service_status(ServiceStatus.ACTIVE)

    def remove_service(self, *, show_no_service_to_remove_msg: bool = True) -> None:
        def _remove_service_files() -> None:
            if Path(settings.system_service_file_path).exists():
                _run_command(f'sudo rm {settings.system_service_file_path}')
            if Path(settings.system_start_script_path).exists():
                _run_command(f'sudo rm {settings.system_start_script_path}')

        service_status, _service_log = self.get_service_status()
        if service_status not in {ServiceStatus.ACTIVE, ServiceStatus.ENABLED_INACTIVE}:
            if show_no_service_to_remove_msg:
                print(f'No service {settings.service_file_name} to remove')
            _remove_service_files()
            return
        print(f'Removing service {settings.service_file_name}')
        _run_command(f'sudo systemctl disable --now {settings.service_file_name}', check=False, raise_std_error=False)
        self.wait_service_status(ServiceStatus.INACTIVE)
        _remove_service_files()
        _run_command('sudo systemctl daemon-reload')

    @staticmethod
    def _get_process_table(process: str) -> tuple[list[str], list[dict[str, str]]]:
        """Get all ID of all running application processes.

        Returns:
            List of running application process id's as row text list and dict table.

        """
        result = _run_command('TZ=UTC ps aux', check=False)
        all_app_proc_output = result.stdout.split('\n')
        header_line = all_app_proc_output[0]
        headers = header_line.split()
        columns = len(headers) - 1
        proc_lines = all_app_proc_output[1:-1]  # First line is the header and last line is empty
        proc_table = []
        proc_output_print_lines = [header_line]
        for proc_line in proc_lines:
            proc_cells = proc_line.split(maxsplit=columns)
            proc_table_line = dict(zip(headers, proc_cells, strict=True))
            if process in proc_table_line['COMMAND']:
                proc_table.append(proc_table_line)
                proc_output_print_lines.append(proc_line)
        if not proc_table:
            proc_output_print_lines = []
        return proc_output_print_lines, proc_table

    def get_application_ids_table(self, *, print_message: bool = True) -> tuple[list[str], list[dict[str, str]]]:
        table_rows, proc_table = self._get_process_table(settings.application_script)
        if proc_table:
            printout = f'Running processes of {settings.application_script}:'
            for output_line in table_rows:
                printout += '\n  ' + output_line
        else:
            printout = f'Process {settings.application_script} is not running.'
        if print_message:
            print(printout)
        return printout, proc_table

    def check(self) -> None:
        service_status, status_log_lines = self.get_service_status()
        status_log = '\n' + status_log_lines if status_log_lines else ''
        print(f'Service status for {settings.service_file_name}: {service_status}{status_log}')
        self.get_application_ids_table()
        self.is_tmux_active(raise_exception=False)

    def stop_application(self, *, msg_no_kill: bool = True) -> None:
        """Stop application on RPI.

        Raises:
            ProcessKillError: If application could not get killed.

        """
        printout, proc_table = self.get_application_ids_table(print_message=False)
        if not proc_table:
            if msg_no_kill:
                print('No running process found, nothing to kill')
            return

        print(printout)
        app_pid_filter = '.venv/bin/python3'
        if not (proc_kill_list := [pid['PID'] for pid in proc_table if app_pid_filter in pid['COMMAND']]):
            error_message = f'There were no PIDs matching the pattern "{app_pid_filter}...{settings.application_script}"'
            raise ProcessKillError(error_message)

        print(f'Killing process "{app_pid_filter}...{settings.application_script}". PID(s): {", ".join(proc_kill_list)}')
        self._stop_application(proc_kill_list)

        printout, proc_table = self.get_application_ids_table(print_message=False)
        if proc_table:
            error_message = f'Still active PID(s)\n{printout}'
            raise ProcessKillError(error_message)
 
    @staticmethod
    def _stop_application(proc_kill_list: list) -> None:
        """Stop application on RPI.

        Raises:
            ProcessKillError: If application could not get killed.

        """
        for pid in proc_kill_list:
            for kill_signal in KillSignals:
                error = f'Failed to kill "{settings.application_script}" (PID {pid}) with {kill_signal.name}'
                result = _run_command(f'kill {kill_signal.value} {pid}', check=False, raise_std_error=False)
                if result.returncode != 0:
                    error_message = f'{error}: {result.stderr.strip()}'
                    raise ProcessKillError(error_message)
                check_reties = 10
                while True:
                    time.sleep(0.2)
                    result = _run_command(f'ps -p {pid}', check=False)
                    if result.returncode != 0:
                        error = ''
                        break
                    check_reties -= 1
                    if check_reties < 0:
                        break
                if not error:
                    break
                print(error)
            if error:
                raise ProcessKillError(error)
            print(f'Successfully killed PID {pid} with {kill_signal.name}')

    def start_application_in_tmux_session(self) -> None:
        print(f'Starting application "{settings.application_script}" in tmux session: {settings.tmux_session_name}')
        self.kill_tmux_session(msg_no_kill=False)
        _run_command(f'tmux new-session -d -s {settings.tmux_session_name}')
        _run_command(f'tmux pipe-pane -t {settings.tmux_session_name}:0.0 -o "cat >> {settings.tmux_log_path}"')
        app_run_command = f'uv run --no-group dev {settings.application_script}'
        _run_command(f'tmux send-keys -t {settings.tmux_session_name}:0.0 "{app_run_command}" C-m')
        print(f'tmux log file: {settings.tmux_log_path}')
        print('TO ENTER TMUX TERMINAL ON DEVICE: make tmux')

    def tmux(self) -> None:
        if not self.is_tmux_active(raise_exception=False):
            print(f'\nThere is no tmux session for {settings.tmux_session_name}!\n')
        _run_command(f'tmux attach -t {settings.tmux_session_name}')

    def kill_tmux_session(self, *, msg_no_kill: bool = True, delete_files: bool = True) -> None:
        if not self.is_tmux_active(raise_exception=False, print_status=msg_no_kill):
            return
        if msg_no_kill: 
            print(f'Killing tmux session: {settings.tmux_session_name}')
        _run_command(f'tmux kill-session -t {settings.tmux_session_name}')
        if self.is_tmux_active(print_status=False):
            kill_error = f'Failed to kill tmux session: {settings.tmux_session_name}'
            raise TmuxSessionKillError(kill_error)
        if delete_files:
            _run_command(f'rm -f {settings.tmux_log_path_search_pattern}', check=False, raise_std_error=True)

    @staticmethod
    def is_tmux_active(*, raise_exception: bool = False, print_status: bool = True) -> bool:
        """Check if application tmux session is active.

        Returns:
            True if tmux session is active, False otherwise.

        """
        if _run_command('tmux ls', check=False, raise_std_error=False).returncode != 0:
            status = False
        else:
            command = f'tmux has-session -t {settings.tmux_session_name}'
            if raise_exception:
                result = _run_command(command)
            else:
                with suppress(subprocess.CalledProcessError):
                    result = _run_command(command)
            status = (result.returncode == 0)
        if print_status:
            print(f'Tmux session of {settings.tmux_session_name} status: {"Active" if status else "Does not exist"}')
        return status


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
