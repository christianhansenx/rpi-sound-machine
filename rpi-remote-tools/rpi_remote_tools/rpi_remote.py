"""Tool functions for RPI Remote control."""
import argparse
import configparser
import enum
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from .ssh_client import SshClient, SshClientHandler

UPLOAD_EXCLUDES_FOLDERS = ['.venv', '.git', '.ruff_cache', '__pycache__']
UPLOAD_EXCLUDES_FILES = []  # Add specific file names here if needed
RPI_HOST_CONFIG_FILE = Path('rpi_host_config.yaml')
RPI_SETTINGS_FILE = 'settings.ini'
RPI_SETTINGS_FILE_SETTINGS_KEYWORD = 'settings'


class RpiRemoteCommandError(Exception):
    """Execution error on RPI."""


class RpiTmuxError(Exception):
    """tmux issue."""


class KillSignals(enum.StrEnum):
    """Kill signals for stopping application on RPI."""

    SIGTERM = '-15'  # Terminate gracefully
    SIGINT = '-2'  # Ctrl+C
    SIGKILL = '-9'  # Force kill


class _RpiSettings(BaseModel):
    """Pydantic model for RPI settings."""

    application_script: str = Field(..., description='The main application file to run on the RPI.')
    tmux_session_name: str = Field(..., description='The tmux session name.')
    tmux_log_path_pattern: str = Field(..., description='The log file path pattern for the tmux session.')


class RpiRemoteToolsConfig(BaseModel):
    """Pydantic model for rpi-remote-tools configuration."""

    project_directory: str = Field(..., description='The local project directory to sync to the RPI.')
    local_project_path: Path = Field(..., description='The local path to sync to RPI.')
    remote_project_folder: str = Field(..., description='The project path on the RPI.')
    rpi_settings: _RpiSettings = Field(..., description='Setting for the application to be located on RPI.')


@dataclass
class RpiCommand:
    """Run command on RPI."""

    ssh_client: SshClient
    project_directory: str
    status: int = field(init=False)
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)

    def command(self, command: str, *, print_stdout: bool = True, ignore_stderr: bool = False) -> int:
        print(f'== Remote command to RPI: {command}')
        command_line = f'cd /home/{self.ssh_client.username}/{self.project_directory} && {command}'
        _stdin, stdout, stderr = self.ssh_client.client.exec_command(command_line)
        self.status = stdout.channel.recv_exit_status()
        self.stdout = stdout.read().decode('utf-8').rstrip().split('\n')
        self.stderr = stderr.read().decode('utf-8').rstrip().split('\n')
        if print_stdout and self.stdout[0]:
            print(f'{"\n".join(self.stdout)}')
        if self.stderr[0]:
            if not ignore_stderr:
                error = f'{"\n".join(self.stderr)}\nRPI command line: {command_line}'
                raise RpiRemoteCommandError(error)
            print(f'WARNING: {"\n".join(self.stderr)}')
        print()
        return self.status


def rpi_get_file_path(ssh_client: SshClient, search_pattern: str, *, raise_no_file_exception: bool = True) -> str | None:
    _stdin, stdout, stderr = ssh_client.client.exec_command(f'ls {search_pattern}')
    status = stdout.channel.recv_exit_status()
    if status:
        no_file_found = 2
        if status != no_file_found:
            error = f'Searching files on RPI: {search_pattern}, stderr={stderr.read().decode('utf-8').strip()}'
            raise RpiTmuxError(error)
        error = f'File not found: {search_pattern}'
        if raise_no_file_exception:
            raise RpiTmuxError(error)
    log_files = stdout.read().decode('utf-8').strip().split('\n')
    log_files.sort()
    return log_files[-1]  # File name with most recent time stamp in the name


def _check_tmux_session(ssh_client: SshClient, session_name: str, log_file: str) -> None:
    """Check tmux session on RPI.

    Raises:
        RpiTmuxError: If tmux session issue.

    """
    rpi_get_file_path(ssh_client, log_file)
    _stdin, stdout, stderr = ssh_client.client.exec_command(f'tmux has-session -t {session_name}')
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        error = (
            f'There is no active tmux session "{session_name}" on {ssh_client.connection}:'
            f'\n{stderr.read().decode('utf-8').strip()}'
        )
        raise RpiTmuxError(error)
    tmux_check_pipe = f'tmux display-message -p -t {session_name}:0.0 "#{{pane_pipe}}"'
    _stdin, stdout, _stderr = ssh_client.client.exec_command(tmux_check_pipe)
    if stdout.read().decode()[0] != '1':
        error = f'There is no tmux piping to log file for session "{session_name}" on {ssh_client.connection}'
        raise RpiTmuxError(error)


def rpi_tmux_terminal_output(ssh_client: SshClient, config: RpiRemoteToolsConfig) -> None:
    session_name = config.rpi_settings.tmux_session_name
    log_file_search_pattern = config.rpi_settings.tmux_log_path_pattern.format(timestamp='*')
    tmux_log_file_path = rpi_get_file_path(ssh_client, log_file_search_pattern)
    _check_tmux_session(ssh_client, session_name, tmux_log_file_path)

    # Set up user termination thread
    stop_event = threading.Event()

    def wait_for_enter() -> None:
        input()  # Waits until the user presses Enter
        stop_event.set()

    input_thread = threading.Thread(target=wait_for_enter, daemon=True)
    input_thread.start()

    sftp_client = ssh_client.client.open_sftp()
    sftp_client.stat(tmux_log_file_path)

    # tmux streaming
    remote_tmux_log = sftp_client.open(tmux_log_file_path, 'r', bufsize=4096)
    print('Press Enter to exit remote tmux session.\n')
    try:
        error_check_time_interval = 3
        error_check_timer_start = time.monotonic()
        while not stop_event.is_set():
            line = remote_tmux_log.readline()
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
            if time.monotonic() - error_check_timer_start > error_check_time_interval:
                _check_tmux_session(ssh_client, session_name, tmux_log_file_path)
                error_check_timer_start = time.monotonic()
            time.sleep(0.02)
    finally:
        remote_tmux_log.close()
        sftp_client.close()


def rpi_upload_app_files(ssh_client: SshClient, config: RpiRemoteToolsConfig) -> None:
    """Upload application files to RPI."""
    all_exclude_patterns = UPLOAD_EXCLUDES_FOLDERS + UPLOAD_EXCLUDES_FILES
    ssh_client.upload_recursive(config.local_project_path, config.remote_project_folder, all_exclude_patterns)


def _get_configurations(configurations_content: str, remote_username: str) -> RpiRemoteToolsConfig:
    try:
        config_data = json.loads(configurations_content)
    except json.JSONDecodeError as exception:
        error_msg = f'Error decoding configurations as JSON:\n{configurations_content}\n'
        raise ValueError(error_msg) from exception
    config_data['remote_project_folder'] = f'/home/{remote_username}/{config_data['project_directory']}'
    local_project_path = (Path(__file__).parent / '..' / '..' / config_data['project_directory']).resolve()
    config_data['local_project_path'] = local_project_path

    settings_file = local_project_path / RPI_SETTINGS_FILE
    if not Path(settings_file).exists():
        error = f'Settings file not found: {settings_file}'
        raise FileNotFoundError(error)
    settings_data = configparser.ConfigParser()
    settings_data.read(settings_file)
    settings = settings_data[RPI_SETTINGS_FILE_SETTINGS_KEYWORD]
    settings['tmux_log_path_pattern'] = settings['tmux_log_path_pattern'].format(
        session_name=settings['tmux_session_name'],
        timestamp=r'{timestamp}',
    )
    config_data['rpi_settings'] = _RpiSettings(**settings)

    return RpiRemoteToolsConfig(**config_data)


def rpi_check_project_exist_and_upload(ssh_client: SshClient, config: RpiRemoteToolsConfig, *, force_upload: bool) -> bool:
    upload = force_upload
    if not force_upload:
        make_file = f'/home/{ssh_client.username}/{config.project_directory}/Makefile'
        if not rpi_get_file_path(ssh_client, make_file, raise_no_file_exception=False):
            print(f'Project Makefile not found on RPI: {make_file}. Upload code first.')
            if input('Would you like to upload the code now? (y/n): ').strip().lower() not in {'y', 'yes'}:
                return False
            upload = True
    if upload:
        rpi_upload_app_files(ssh_client, config)
        print()
    return True


def rpi_install(rpi_command: RpiCommand) -> None:
    no_frontend = 'DEBIAN_FRONTEND=noninteractive'  # To avoid some interactive questions
    if input('Do you want to skip "apt-get-update"? (Y/n): ').strip() not in {'Y', 'YES'}:
        print()
        rpi_command.command(f'sudo {no_frontend} apt-get update')
        rpi_command.command(f'sudo {no_frontend} apt-get upgrade -y')
        rpi_command.command(f'sudo {no_frontend} apt-get install -y')
    else:
        print()
    rpi_command.command(f'sudo {no_frontend} apt-get install tmux -y')

    rpi_command.command(f'sudo {no_frontend} apt install snapd -y')
    rpi_command.command('snap changes')  # Wait for snapd to be ready
    rpi_command.command(f'sudo {no_frontend} snap install snapd', ignore_stderr=True)  # Ignore "already installed)"
    rpi_command.command(f'sudo {no_frontend} snap install astral-uv --classic', ignore_stderr=True)  # Ignore "already installed)"


def execute_commands(args: argparse.Namespace) -> None:
    with SshClientHandler(RPI_HOST_CONFIG_FILE) as ssh_client:
        config = _get_configurations(args.configurations, ssh_client.username)
        rpi_command = RpiCommand(ssh_client=ssh_client, project_directory=config.project_directory)

        if not rpi_check_project_exist_and_upload(ssh_client, config, force_upload=args.rpi_upload_code):
            return
        if args.rpi_install:
            rpi_install(rpi_command)
        if args.rpi_stop_app or args.rpi_stop or args.rpi_restart:
            rpi_command.command('make stop-app')
            rpi_command.command('make kill-tmux')
        if args.rpi_stop:
            rpi_command.command('make stop-service')
        if args.rpi_restart:
            rpi_command.command('make start-service')
        if args.rpi_run_app_in_tmux:
            rpi_command.command('make run')
        if args.rpi_tmux or args.rpi_run_app_in_tmux:
            rpi_tmux_terminal_output(ssh_client, config)
        if args.rpi_check:
            rpi_command.command('make check')


def main() -> None:
    """Call functions depending on script arguments."""
    print(f'Python version: {sys.version_info.major}.{sys.version_info.minor}')

    parser = argparse.ArgumentParser(description='Raspberry Pi Remote Tools etc.')
    parser.add_argument(
        '--rpi-install',
        action='store_true',
        help='Installing system applications on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-upload-code',
        action='store_true',
        help='Copy code recursively to the Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-check',
        action='store_true',
        help='Check about logger application is already running on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-stop-app',
        action='store_true',
        help='Kill application on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-stop',
        action='store_true',
        help='Stop application and service on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-restart',
        action='store_true',
        help='Restart application service on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-run-app-in-tmux',
        action='store_true',
        help='Run application on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-tmux',
        action='store_true',
        help='Live stream from Raspberry Pi device tmux session',
    )
    parser.add_argument(
        '--configurations',
        type=str,
        required=True,
        help='JSON string with the configuration',
    )

    execute_commands(parser.parse_args())


if __name__ == '__main__':
    main()
