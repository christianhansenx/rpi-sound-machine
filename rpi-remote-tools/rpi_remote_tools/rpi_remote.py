"""Tool functions for RPI Remote control."""
import argparse
import enum
import errno
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import yaml
from paramiko import SFTPClient
from pydantic import BaseModel, Field, computed_field

from .ssh_client import SshClient, SshClientHandler

UPLOAD_EXCLUDES_FOLDERS = ['.venv', '.git', '.ruff_cache', '__pycache__']
UPLOAD_EXCLUDES_FILES = []  # Add specific file names here if needed
RPI_HOST_CONFIG_FILE = Path('rpi_host_config.yaml')
RPI_SETTINGS_FILE = Path('settings.mk')


class RpiRemoteCommandError(Exception):
    """Execution error on RPI."""


class StartRpiTmuxError(Exception):
    """Could not start tmux session on RPI."""


class KillSignals(enum.StrEnum):
    """Kill signals for stopping application on RPI."""

    SIGTERM = '-15'  # Terminate gracefully
    SIGINT = '-2'  # Ctrl+C
    SIGKILL = '-9'  # Force kill


class _RpiSettings(BaseModel):
    """Pydantic model for RPI settings."""

    application_script: str = Field(..., description='The main application file to run on the RPI.')
    tmux_session_name: str = Field(..., description='The tmux session name.')
    tmux_log_file_pattern: str = Field(..., description='The log file path pattern for the tmux session.')


class RpiRemoteToolsConfig(BaseModel):
    """Pydantic model for rpi-remote-tools configuration."""

    project_directory: str = Field(..., description='The local project directory to sync to the RPI.')
    remote_project_folder: str = Field(..., description='The project path on the RPI.')

    @computed_field
    @cached_property
    def local_project_path(self) -> Path:
        return (Path(__file__).parent / '..' / '..' / self.project_directory).resolve()

    @computed_field
    @cached_property
    def rpi_settings(self) -> _RpiSettings:
        rpi_settings_file_path = self.local_project_path / RPI_SETTINGS_FILE

        settings = {}
        with rpi_settings_file_path.open('r', encoding='utf-8') as f:
            contents = f.read()
        for file_line in contents.splitlines():
            line = file_line.strip()
            if not line or line.startswith("#"):
                continue
            if ':=' in line:
                key, value = line.split(':=', 1)
                settings[key.strip().lower()] = value.strip()
        settings['tmux_log_file_pattern'] = settings['tmux_log_file_pattern'].format(
            session_name=settings['tmux_session_name'],
            timestamp=r'{timestamp}',
        )
        return _RpiSettings(**settings)


@dataclass
class RpiCommand:
    """Run command on RPI."""

    ssh_client: SshClient
    project_directory: str
    status: int = field(init=False)
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)

    def command(self, command: str, *, print_stdout: bool = True) -> None:
        print(f'== Remote command to RPI: {command}')
        command_line = f'cd /home/{self.ssh_client.username}/{self.project_directory} && {command}'
        _stdin, stdout, stderr = self.ssh_client.client.exec_command(command_line)
        self.status = stdout.channel.recv_exit_status()
        self.stdout = stdout.read().decode('utf-8').rstrip().split('\n')
        self.stderr = stderr.read().decode('utf-8').rstrip().split('\n')
        if self.stderr[0]:
            error = f'{"\n".join(self.stderr)}\nRPI command line: {command_line}'
            raise RpiRemoteCommandError(error)
        if print_stdout:
            print(f'{"\n".join(self.stdout)}')
        print()


def rpi_application_process_ids(ssh_client: SshClient, config: RpiRemoteToolsConfig) -> None:
    rpi_command = RpiCommand(ssh_client=ssh_client, project_directory=config.project_directory)
    rpi_command.command('make process-id')


def rpi_stop_application(ssh_client: SshClient, config: RpiRemoteToolsConfig) -> None:
    rpi_command = RpiCommand(ssh_client=ssh_client, project_directory=config.project_directory)
    rpi_command.command('make stop')


def rpi_run(ssh_client: SshClient, config: RpiRemoteToolsConfig) -> None:
    rpi_command = RpiCommand(ssh_client=ssh_client, project_directory=config.project_directory)
    rpi_command.command('make run')


def _rpi_tmux_get_log_file_path(ssh_client: SshClient, config: RpiRemoteToolsConfig) -> str | None:
    log_files_search_pattern = config.rpi_settings.tmux_log_file_pattern.format(timestamp='*')
    _stdin, stdout, stderr = ssh_client.client.exec_command(f'ls {log_files_search_pattern}')
    status = stdout.channel.recv_exit_status()
    if status:
        no_file_found = 2
        if status == no_file_found:
            return None
        error = f'Searching files on RPI: {log_files_search_pattern}, stderr={stderr.read().decode('utf-8').strip()}'
        raise StartRpiTmuxError(error)
    log_files = stdout.read().decode('utf-8').strip().split('\n')
    log_files.sort()
    return log_files[-1]


def rpi_tmux(
        ssh_client: SshClient,
        process_name: str,
        config: RpiRemoteToolsConfig,
        *,
        restart_application: bool = False,
) -> None:
    """Open tmux session on RPI.

    If restart_application is True, the application will be started in the tmux session.

    Raises:
        StartRpiTmuxError: If tmux session could not be started.

    """
    tmux_log_file_path = _rpi_tmux_get_log_file_path(ssh_client, config)
    if not tmux_log_file_path:
        print('No log file found on rpi')
    else:
        print(f'log file on rpi: {tmux_log_file_path}')
    exit()

    # Restart tmux session if required
    tmux_command = None
    if restart_application:
        _stdin, stdout, stderr = ssh_client.client.exec_command(f'{config.remote_project_folder}/start-tmux.sh')
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            error = (
                f'Could not open tmux session "{config.tmux_session_name}" on {ssh_client.connection}:'
                f'\n{stderr.read().decode().strip()}',
            )
            raise StartRpiTmuxError(error)

    else:
        _stdin, stdout, stderr = ssh_client.client.exec_command(f'tmux has-session -t {config.tmux_session_name}')
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            error = (
                f'Could not open tmux session "{config.tmux_session_name}" on {ssh_client.connection}:'
                f'\n{stderr.read().decode().strip()}',
            )
            raise StartRpiTmuxError(error)
        tmux_check_pipe = f'tmux display-message -p -t {config.tmux_session_name}:0.0 "#{{pane_pipe}}"'
        _stdin, stdout, stderr = ssh_client.client.exec_command(tmux_check_pipe)
        if stdout.read().decode()[0] != '1':
            tmux_command = (
                f'rm {tmux_log_file_path} 2>/dev/null; '
                f'tmux pipe-pane -t {config.tmux_session_name}:0.0 -o "cat >> {tmux_log_file_path}"'
            )

    if tmux_command:
        ssh_client.client.exec_command(tmux_command)
        time.sleep(1)

    _tmux_terminal(ssh_client, process_name, tmux_log_file_path, config, restart_application=restart_application)


def _tmux_terminal(
        ssh_client: SshClient, process_name: str,
        tmux_log_file_path: str,
        config: RpiRemoteToolsConfig,
        *,
        restart_application: bool,
) -> None:
    # start sftp
    max_retries = 10
    sftp_client = None
    for _ in range(max_retries):
        try:
            sftp_client = ssh_client.client.open_sftp()
            sftp_client.stat(tmux_log_file_path)
            break
        except OSError as e:
            if e.errno == errno.ENOENT:  # File not found
                time.sleep(0.5)
            else:
                raise
    else:
        error = f'Failed to find log file on rpi: {tmux_log_file_path}'
        raise FileNotFoundError(error)

    # Start application (if required)
    if restart_application:
        ssh_client.client.exec_command(f'{config.remote_project_folder}/start.sh')
        print(f'Application {config.rpi_settings.application_script} on {ssh_client.connection} has been started')

    _tmux_terminal_streaming(ssh_client, process_name, tmux_log_file_path, config, sftp_client)


def _tmux_terminal_streaming(
    ssh_client: SshClient,
    process_name: str,
    tmux_log_file_path: str,
    config: RpiRemoteToolsConfig,
    sftp_client: SFTPClient,
) -> None:
    tmux_session_msg = (
        f'\ntmux session "{config.tmux_session_name}" is running on {ssh_client.connection}, to access it from rpi terminal:'
        f' tmux attach -t {config.tmux_session_name}'
    )

    # Set up user termination thread
    stop_event = threading.Event()

    def wait_for_enter() -> None:
        input()  # Waits until the user presses Enter
        print(f'{tmux_session_msg}')
        stop_event.set()

    input_thread = threading.Thread(target=wait_for_enter, daemon=True)
    input_thread.start()

    # tmux streaming
    remote_tmux_log = sftp_client.open(tmux_log_file_path, 'r', bufsize=4096)
    mux_log_creation_time = remote_tmux_log.stat().st_mtime
    print(f'{tmux_session_msg}')
    check_app_reties = 10
    while True:
        if _rpi_check_running_app(ssh_client, process_name):
            break
        check_app_reties -= 1
        if check_app_reties < 0:
            print(f'WARNING: No running process found of "{process_name}"')
            break
        time.sleep(0.2)
    print('Press Enter to exit remote tmux session.\n')
    try:
        while not stop_event.is_set():
            line = remote_tmux_log.readline()
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
            else:
                time.sleep(0.5)
                if sftp_client.stat(tmux_log_file_path).st_mtime != mux_log_creation_time:
                    error = 'Log file was deleted and recreated.'
                    raise RuntimeError(error)
    finally:
        remote_tmux_log.close()
        sftp_client.close()
        print('tmux closed')


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
    return RpiRemoteToolsConfig(**config_data)


def main() -> None:
    """Call functions depending on script arguments."""
    print(f'Python version: {sys.version_info.major}.{sys.version_info.minor}')

    parser = argparse.ArgumentParser(description='Raspberry Pi Remote Tools etc.')
    parser.add_argument(
        '--rpi-check-app',
        action='store_true',
        help='Check about logger application is already running on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-kill-app',
        action='store_true',
        help='Kill application on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-run-app',
        action='store_true',
        help='Run application on Raspberry Pi device',
    )
    parser.add_argument(
        '--rpi-copy-code',
        action='store_true',
        help='Copy code recursively to the Raspberry Pi device',
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

    args = parser.parse_args()

    with SshClientHandler(RPI_HOST_CONFIG_FILE) as ssh_client:
        config = _get_configurations(args.configurations, ssh_client.username)
        rpi_application_process_name = f'python3 {config.rpi_settings.application_script}'
        if args.rpi_check_app:
            rpi_application_process_ids(ssh_client, config)
        elif args.rpi_kill_app:
            rpi_stop_application(ssh_client, config)
        elif args.rpi_run_app:
            rpi_run(ssh_client, config)
        elif args.rpi_tmux:
            rpi_tmux(ssh_client, rpi_application_process_name, config)
        elif args.rpi_copy_code:
            rpi_upload_app_files(ssh_client, config)
            # rpi_stop_application(ssh_client, config)
            # rpi_tmux(ssh_client, rpi_application_process_name, config, restart_application=True)


if __name__ == '__main__':
    main()
