"""Tool functions for RPI Remote control."""
import argparse
import enum
import errno
import json
import sys
import threading
import time
from pathlib import Path

from paramiko import SFTPClient
from pydantic import BaseModel, Field

from .ssh_client import SshClient, SshClientHandler

UPLOAD_EXCLUDES_FOLDERS = ['.venv', '.git', '.ruff_cache', '__pycache__']
UPLOAD_EXCLUDES_FILES = []  # Add specific file names here if needed
RPI_HOST_CONFIG_FILE = Path('rpi_host_config.yaml')

# Linting: S108 Probable insecure usage of temporary file or directory: "/tmp/"
TMUX_LOG_PATH = '/tmp/{file_name}.tmux-log'  # noqa: S108


class StartRpiTmuxError(Exception):
    """Could not start tmux session on RPI."""


class KillRpiProcessError(Exception):
    """Could not kill application on RPI."""


class InstallRpiTmuxError(Exception):
    """Could not install tmux on RPI."""


class KillSignals(enum.StrEnum):
    """Kill signals for stopping application on RPI."""

    SIGTERM = '-15'  # Terminate gracefully
    SIGINT = '-2'  # Ctrl+C
    SIGKILL = '-9'  # Force kill


class RpiRemoteToolsConfig(BaseModel):
    """Pydantic model for rpi-remote-tools configuration."""

    local_project_directory: str = Field(..., description='The local project directory to sync to the RPI.')
    application_file: str = Field(..., description='The main application file to run on the RPI.')
    tmux_session_name: str = Field(..., description='The name of the tmux session to use on the RPI.')


def rpi_check_running_app(ssh_client: SshClient, process_name: str, *, message_no_process: bool = True) -> list[str]:
    """Check about processes are running.

    Returns:
        list of running process id's

    """
    proc_ids = _rpi_check_running_app(ssh_client, process_name)
    valid_proc_ids = [pid for pid in proc_ids if pid]
    if valid_proc_ids:
        print(f'Process "{process_name}" running')
        print(f'Found existing PID(s): {", ".join(valid_proc_ids)}')
    elif message_no_process:
        print(f'No existing process found of "{ssh_client.connection} {process_name}"')
    return valid_proc_ids


def _rpi_check_running_app(ssh_client: SshClient, process_name: str) -> list[str]:
    _stdin, stdout, _stderr = ssh_client.client.exec_command(f'pgrep -f "{process_name}"')
    proc_ids = stdout.read().decode('utf-8').strip().split('\n')
    return [pid for pid in proc_ids if pid]


def rpi_kill_app(ssh_client: SshClient, process_name: str, *, msg_no_kill: bool = True) -> None:
    """Stop application on RPI.

    Raises:
        KillRpiProcessError: If application could not get killed.

    """
    if not (proc_ids := _rpi_check_running_app(ssh_client, process_name)):
        if msg_no_kill:
            print('No running process found, nothing to kill')
        return
    print(f'Killing process "{process_name}" with PID(s): {", ".join(proc_ids)}')
    kill_error = 'unknown error'
    for kill_signal in KillSignals:
        for pid in proc_ids:
            if _rpi_check_process_id(ssh_client, pid):
                _stdin, stdout, stderr_kill = ssh_client.client.exec_command(f'kill {kill_signal.value} {pid}')
                exit_status = stdout.channel.recv_exit_status()
                if exit_status != 0:
                    error = (
                        f'Failed to kill "{process_name}" (PID {pid}) with {kill_signal.name}: '
                        f'{stderr_kill.read().decode('utf-8').strip()}'
                    )
                    raise KillRpiProcessError(error)
                time.sleep(0.2)
        if not (kill_error := _rpi_wait_no_kill_error(ssh_client, process_name, kill_signal)):
            break

    else:
        raise KillRpiProcessError(kill_error)
    print(f'Successfully killed "{process_name}" with {kill_signal.name}')


def _rpi_wait_no_kill_error(ssh_client: SshClient, process_name: str, kill_signal: KillSignals) -> str | None:
    kill_error = None
    check_reties = 10
    while True:
        if not (proc_ids := _rpi_check_running_app(ssh_client, process_name)):
            break
        check_reties -= 1
        if check_reties < 0:
            kill_error = f'Failed to kill "{process_name}" with {kill_signal.name}, PID(s) still alive: {", ".join(proc_ids)}'
            print(f'{kill_error}')
            break
        time.sleep(0.2)
    return kill_error


def _rpi_check_process_id(ssh_client: SshClient, proc_id: str) -> bool:
    """Check about process is running.

    Returns:
        True if process is running.

    """
    _stdin, stdout, _stderr = ssh_client.client.exec_command(f'ps -p {proc_id}')
    exit_status = stdout.channel.recv_exit_status()
    return exit_status == 0


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
    tmux_log_file_path = TMUX_LOG_PATH.format(file_name=config.local_project_directory)

    # Restart tmux session if required
    _install_tmux(ssh_client)
    tmux_command = None
    if restart_application:
        remote_dir = f'/home/{ssh_client.username}/{config.local_project_directory}'
        ssh_client.client.exec_command(f'{remote_dir}/start-mux.sh')

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
        remote_dir = f'/home/{ssh_client.username}/{config.local_project_directory}'
        ssh_client.client.exec_command(f'{remote_dir}/start.sh')
        print(f'Application {config.application_file} on {ssh_client.connection} has been started')

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
    finally:
        remote_tmux_log.close()
        sftp_client.close()
        print('tmux closed')


def _install_tmux(ssh_client: SshClient) -> None:
    """Installs tmux on the remote Raspberry Pi (if not already installed).

    Raises:
        InstallRpiTmuxError: If installation fails.

    """
    _stdin, stdout, stderr = ssh_client.client.exec_command('which tmux')
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        print(f'Installing tmux on {ssh_client.connection}')
        _stdin, stdout, stderr = ssh_client.client.exec_command('sudo apt install tmux -y')
        stdout_output = stdout.read().decode()
        stderr_output = stderr.read().decode()
        for line in stdout_output.splitlines():
            print(f'\t{line}')
        for line in stderr_output.splitlines():
            print(f'\t{line}')
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            error = f'Installation failed on {ssh_client.connection}:\n{stderr_output.strip()}'
            raise InstallRpiTmuxError(error)


def rpi_upload_app_files(ssh_client: SshClient, config: RpiRemoteToolsConfig) -> None:
    """Upload application files to RPI."""
    all_exclude_patterns = UPLOAD_EXCLUDES_FOLDERS + UPLOAD_EXCLUDES_FILES
    ssh_client.upload_recursive(config.local_project_directory, all_exclude_patterns)


def _get_configurations(configurations_content: str) -> RpiRemoteToolsConfig:
    try:
        config_data = json.loads(configurations_content)
    except json.JSONDecodeError as exception:
        error_msg = f'Error decoding configurations as JSON:\n{configurations_content}\n'
        raise ValueError(error_msg) from exception

    script_dir = Path(__file__).parent
    tmux_file = (script_dir / '..' / '..' / config_data['local_project_directory']).resolve() / 'start-tmux.sh'
    with Path.open(tmux_file, 'r', encoding='utf-8') as file:
        file_content = file.read()
    session_name = None
    session_variable = 'TMUX_SESSION_NAME='
    for line in file_content.splitlines():
        if line.startswith(session_variable):
            session_name = line.split('=', 1)[1].strip().strip('"')
            break
    if not session_name:
        error_msg = f'Could not find {session_variable} in {tmux_file}'
        raise ValueError(error_msg)
    config_data['tmux_session_name'] = session_name

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
    config = _get_configurations(args.configurations)
    rpi_application_process_name = f'python3 {config.application_file}'

    with SshClientHandler(RPI_HOST_CONFIG_FILE) as ssh_client:
        if args.rpi_check_app:
            rpi_check_running_app(ssh_client, rpi_application_process_name)
        elif args.rpi_kill_app:
            rpi_kill_app(ssh_client, rpi_application_process_name)
        elif args.rpi_run_app:
            rpi_kill_app(ssh_client, rpi_application_process_name, msg_no_kill=False)
            rpi_tmux(ssh_client, rpi_application_process_name, config, restart_application=True)
        elif args.rpi_tmux:
            rpi_tmux(ssh_client, rpi_application_process_name, config)
        elif args.rpi_copy_code:
            rpi_kill_app(ssh_client, rpi_application_process_name, msg_no_kill=False)
            rpi_upload_app_files(ssh_client, config)
            rpi_tmux(ssh_client, rpi_application_process_name, config, restart_application=True)


if __name__ == '__main__':
    main()
