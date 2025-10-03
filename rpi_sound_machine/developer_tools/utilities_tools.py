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
LOCAL_SERVICE_DIRECTORY = Path(__file__).parent / '..' / 'system-service'


class TerminalColors:
    """ANSI escape codes for colors and styles."""

    # Styles
    RESET = '\033[0m'
    BOLD = '\033[1m'

    # Foreground Colors
    BLACK = '\033[30m'  # Standard Black
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    CYAN = '\033[36m'
    BRIGHT_MAGENTA = '\033[95m'
    DARK_GRAY = '\033[90m'
    LIGHT_GRAY = '\033[97m'
    WHITE = '\033[37m'

    STATUS_HEADER = BOLD + GREEN
    PROCESS_TABLE_HEADER = BOLD


class ServiceError(Exception):
    """Could not perform service request."""


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


def run_command(command: str, *, check: bool = True, raise_std_error: bool = True) -> subprocess.CompletedProcess:
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
        setting_path = Path(__file__).parent / '..' / SETTINGS_FILE
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
        self.tmux_log_path_search_pattern = Path(tmux_log_path_pattern.format(timestamp='*'))
        self.tmux_log_bak_path_search_pattern = Path(tmux_log_path_pattern.format(timestamp='*') + '.bak')
        timestamp = datetime.now(tz=ZoneInfo('UTC')).strftime('%Y%m%d-%H%M%S')
        self.tmux_log_path = Path(tmux_log_path_pattern.format(timestamp=timestamp))


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

        result = run_command(f'TZ=UTC systemctl status {settings.service_file_name}', check=False, raise_std_error=False)
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
        self.stop_application(show_messages=False)
        self.kill_tmux_session(show_messages=False)
        self.remove_service(show_no_service_to_remove_msg=False)
        self.start_service()

    def start_service(self) -> None:
        if _files_are_different(settings.local_start_script, settings.system_start_script_path):
            run_command(f'sudo chmod +x {settings.local_start_script}')
            run_command(f'sudo cp {settings.local_start_script} {settings.system_start_script_path}')
        if _files_are_different(settings.local_service_file, settings.system_service_file_path):
            run_command(f'sudo cp {settings.local_service_file} {settings.system_service_file_path}')

        run_command(f'sudo systemctl enable {settings.service_file_name}', check=False, raise_std_error=False)
        self.wait_service_status(ServiceStatus.ENABLED_INACTIVE)
        run_command(f'sudo systemctl start {settings.service_file_name}')
        run_command('sudo systemctl daemon-reload')
        self.wait_service_status(ServiceStatus.ACTIVE)
        print(f'Service "{settings.service_file_name}" has been started successfully!')

    def remove_service(self, *, show_no_service_to_remove_msg: bool = True) -> None:
        def _remove_service_files() -> None:
            if Path(settings.system_service_file_path).exists():
                run_command(f'sudo rm {settings.system_service_file_path}')
            if Path(settings.system_start_script_path).exists():
                run_command(f'sudo rm {settings.system_start_script_path}')

        service_status, _service_log = self.get_service_status()
        if service_status not in {ServiceStatus.ACTIVE, ServiceStatus.ENABLED_INACTIVE}:
            if show_no_service_to_remove_msg:
                print(f'There is no service "{settings.service_file_name}" to remove!')
            _remove_service_files()
            return
        print(f'Removing service {settings.service_file_name}')
        run_command(f'sudo systemctl disable --now {settings.service_file_name}', check=False, raise_std_error=False)
        self.wait_service_status(ServiceStatus.INACTIVE)
        _remove_service_files()
        run_command('sudo systemctl daemon-reload')

    @staticmethod
    def _get_process_table(process: str) -> tuple[list[str], list[dict[str, str]]]:
        """Get all ID of all running application processes.

        Returns:
            List of running application process id's as row text list and dict table.

        """
        result = run_command('TZ=UTC ps aux', check=False)
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
            printout = (
                f'{TerminalColors.STATUS_HEADER}Running processes of "{settings.application_script}":{TerminalColors.RESET}'
            )
            table_rows[0] = TerminalColors.PROCESS_TABLE_HEADER + table_rows[0] + TerminalColors.RESET
            for output_line in table_rows:
                printout += '\n  ' + output_line
        else:
            printout = (
                f'{TerminalColors.STATUS_HEADER}Process "{settings.application_script}"{TerminalColors.RESET} is not running.'
            )
        if print_message:
            print(printout)
        return printout, proc_table

    def check(self) -> None:
        service_status, status = self.get_service_status()
        max_lines = 15
        status_log_lines = status.strip().splitlines()[:max_lines]
        status_log = '\n  ' + '\n  '.join(status_log_lines) if status_log_lines else ''
        print(
            f'{TerminalColors.STATUS_HEADER}System service "{settings.service_file_name}" status:{TerminalColors.RESET}',
            f'{service_status}{status_log}',
        )
        self.get_application_ids_table()
        self.is_tmux_active(raise_exception=False)

    def stop_application(self, *, show_messages: bool = True) -> None:
        """Stop application on RPI.

        Raises:
            ProcessKillError: If application could not get killed.

        """
        printout, proc_table = self.get_application_ids_table(print_message=False)
        if not proc_table:
            if show_messages:
                print(f'There is no running process "{settings.application_script}" found, nothing to kill!')
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
                result = run_command(f'kill {kill_signal.value} {pid}', check=False, raise_std_error=False)
                if result.returncode != 0:
                    error_message = f'{error}: {result.stderr.strip()}'
                    raise ProcessKillError(error_message)
                check_reties = 10
                while True:
                    time.sleep(0.2)
                    result = run_command(f'ps -p {pid}', check=False)
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
        self.kill_tmux_session(show_messages=False)
        run_command(f'tmux new-session -d -s {settings.tmux_session_name}')
        run_command(f'tmux pipe-pane -t {settings.tmux_session_name}:0.0 -o "cat >> {settings.tmux_log_path}"')
        app_run_command = f'uv run --no-group dev {settings.application_script}'
        run_command(f'tmux send-keys -t {settings.tmux_session_name}:0.0 "{app_run_command}" C-m')
        print(f'Tmux log file: {settings.tmux_log_path}')
        print('TO ENTER TMUX TERMINAL ON DEVICE: make tmux')

    def tmux(self) -> None:
        if not self.is_tmux_active(raise_exception=False, print_status=False):
            print(f'\nThere is no tmux session for {settings.tmux_session_name}!\n')
        run_command(f'tmux attach -t {settings.tmux_session_name}')

    @staticmethod
    def _get_file_paths_sorted(search_pattern: str, *, raise_no_file_exception: bool = False) -> list[Path]:
        search_dir = Path(search_pattern).parent
        name_pattern = Path(search_pattern).name
        files = sorted([Path(file_path) for file_path in search_dir.glob(name_pattern)])
        if not files:
            error = f'No file found: {search_pattern}'
            if raise_no_file_exception:
                raise FileNotFoundError(error)
        return files

    def kill_tmux_session(self, *, show_messages: bool = True) -> None:
        if self.is_tmux_active(raise_exception=False, print_status=False):
            if show_messages:
                print(f'Killing tmux session: {settings.tmux_session_name}')
            run_command(f'tmux kill-session -t {settings.tmux_session_name}')
            if self.is_tmux_active(print_status=False):
                kill_error = f'Failed to kill tmux session: {settings.tmux_session_name}'
                raise TmuxSessionKillError(kill_error)
        elif show_messages:
            print(f'There is no tmux session for "{settings.tmux_session_name}" to close!\n')
        if file_paths := self._get_file_paths_sorted(settings.tmux_log_path_search_pattern):
            file_path = file_paths[-1]
            backup_file_path = file_path.with_name(file_path.name + '.bak')
            file_path.rename(backup_file_path)
            print(f'Tmux backup file created: {backup_file_path}')
            for file_path in file_paths:
                file_path.unlink(missing_ok=True)
        if bak_file_paths := self._get_file_paths_sorted(settings.tmux_log_bak_path_search_pattern):
            for bak_file_path in bak_file_paths[:-1]:
                bak_file_path.unlink(missing_ok=True)

    @staticmethod
    def is_tmux_active(*, raise_exception: bool = False, print_status: bool = True) -> bool:
        """Check if application tmux session is active.

        Returns:
            True if tmux session is active, False otherwise.

        """
        if run_command('tmux ls', check=False, raise_std_error=False).returncode != 0:
            status = False
        else:
            command = f'tmux has-session -t {settings.tmux_session_name}'
            if raise_exception:
                result = run_command(command)
            else:
                with suppress(subprocess.CalledProcessError):
                    result = run_command(command)
            status = (result.returncode == 0)
        if print_status:
            print(
                f'{TerminalColors.STATUS_HEADER}Tmux session "{settings.tmux_session_name}":{TerminalColors.RESET}',
                f'{"is active" if status else "session does not exist"}',
            )
        return status

    def make_files_executable() -> None:
        """Make files executable.

        Traverses all directories from the current location and changes the
        permissions of all .sh files to be executable.
        """
        app_root_path = Path(__file__).resolve().parent
        print(f'Apply execute permission to selected files in: {app_root_path}')
        for filepath in app_root_path.rglob('*.sh'):
            if filepath.is_file():
                filepath.chmod(0o755)


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
            run_command('sudo apt-get update')
            self._skip_apt_get_update = True

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def is_snap_installed() -> bool:
        """Check if snap is installed.

        Returns:
            True if snap is installed, False otherwise.

        """
        try:
            run_command('which snap', check=True)
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
