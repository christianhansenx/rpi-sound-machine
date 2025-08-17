"""Tools for RPI Sound Machine."""
import argparse
import errno
import sys
import threading
import time
from pathlib import Path

from ssh_client import SshClient, SshClientHandler

LOCAL_PROJECT_DIRECTORY = 'rpi_sound_machine'
APPLICATION_FILE = 'sound_machine.py'
TMUX_SESSION_NAME = 'sound'
UPLOAD_EXCLUDES_FOLDERS = ['.venv', '.git', '.ruff_cache', '__pycache__']
UPLOAD_EXCLUDES_FILES = []  # Add specific file names here if needed
RPI_APPLICATION_PROCESS_NAME = f'{LOCAL_PROJECT_DIRECTORY}/.venv/bin/python3 {APPLICATION_FILE}'
CONFIG_FILE = Path('rpi_host_config.yaml')

# Linting: S108 Probable insecure usage of temporary file or directory: "/tmp/"
TMUX_LOG_PATH = f'/tmp/{LOCAL_PROJECT_DIRECTORY}.tmux-log'  # noqa: S108


class StartRpiTmuxError(Exception):
    """Could start tmux session on RPI."""


class KillRpiProcessError(Exception):
    """Could not kill application on RPI."""


class InstallRpiTmuxError(Exception):
    """Could not install tmux on RPI."""


def rpi_check_running_app(ssh_client: SshClient, process_name: str, *, message_no_process: bool = True) -> list[str]:
    """Check about processes are running.

    return: list of running process id's
    """
    stdin, stdout, stderr = ssh_client.client.exec_command(f'pgrep -f "{process_name}"')
    proc_ids = stdout.read().decode('utf-8').strip().split('\n')
    valid_proc_ids = [pid for pid in proc_ids if pid]
    if valid_proc_ids:
        print(f'Process "{process_name}" running')
        print(f'Found existing PID(s): {", ".join(valid_proc_ids)}')
    elif message_no_process:
        print(f'No existing process found of "{ssh_client.connection} {process_name}"')
    return valid_proc_ids


def _rpi_check_process_id(ssh_client: SshClient, proc_id: str) -> bool:
    """Check about process is running."""
    stdin, stdout, stderr = ssh_client.client.exec_command(f'ps -p {proc_id}')
    exit_status = stdout.channel.recv_exit_status()
    return exit_status == 0


def rpi_kill_app(ssh_client: SshClient, process_name: str, proc_ids: list[str], *, msg_no_kill: bool = True) -> None:
    """Stop application on RPI."""
    if not proc_ids:
        if msg_no_kill:
            print('No running process found, nothing to kill')
        return
    for pid in proc_ids:
        if _rpi_check_process_id(ssh_client, pid):
            stdin, stdout, stderr_kill = ssh_client.client.exec_command(f'kill {pid}')
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error = f'Failed to kill PID {pid}: {stderr_kill.read().decode('utf-8').strip()}'
                raise KillRpiProcessError(error)
            time.sleep(0.5)
    time.sleep(1)
    print(f'Successfully killed "{process_name}"')


def rpi_tmux(ssh_client: SshClient, *, restart_application: bool = False) -> None:
    """Open tmux session on RPI."""
    # Restart session if required
    _install_tmux(ssh_client)
    tmux_command = None
    if restart_application:
        tmux_command = (
            f'tmux kill-session -t {TMUX_SESSION_NAME} 2>/dev/null; '
            f'rm {TMUX_LOG_PATH} 2>/dev/null; '
            f'tmux new-session -d -s {TMUX_SESSION_NAME} \\; '
            f'pipe-pane -t {TMUX_SESSION_NAME}:0.0 -o "cat >> {TMUX_LOG_PATH}"'
        )
        ssh_client.client.exec_command(tmux_command)
    else:
        stdin, stdout, stderr = ssh_client.client.exec_command(f'tmux has-session -t {TMUX_SESSION_NAME}')
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            error = (
                f'Could not open tmux session "{TMUX_SESSION_NAME}" on {ssh_client.connection}:'
                f'\n{stderr.read().decode().strip()}',
            )
            raise StartRpiTmuxError(error)
        tmux_check_pipe = f'tmux display-message -p -t {TMUX_SESSION_NAME}:0.0 "#{{pane_pipe}}"'
        stdin, stdout, stderr = ssh_client.client.exec_command(tmux_check_pipe)
        if stdout.read().decode()[0] != '1':
            tmux_command = (
                f'rm {TMUX_LOG_PATH} 2>/dev/null; '
                f'tmux pipe-pane -t {TMUX_SESSION_NAME}:0.0 -o "cat >> {TMUX_LOG_PATH}"'
            )
    if tmux_command:
        ssh_client.client.exec_command(tmux_command)
        time.sleep(1)

    _tmux_terminal(ssh_client, restart_application=restart_application)


def _tmux_terminal(ssh_client: SshClient, *, restart_application: bool) -> None:
    tmux_session_msg = (
        f'\ntmux session "{TMUX_SESSION_NAME}" is running on {ssh_client.connection}, to access it from rpi terminal:'
        f' tmux attach -t {TMUX_SESSION_NAME}'
        '\n'
    )

    # start sftp
    max_retries = 10
    sftp_client = None
    for _ in range(max_retries):
        try:
            sftp_client = ssh_client.client.open_sftp()
            sftp_client.stat(TMUX_LOG_PATH)
            break
        except OSError as e:
            if e.errno == errno.ENOENT:  # File not found
                time.sleep(0.5)
            else:
                raise
    else:
        error = f'Failed to find log file on rpi: {TMUX_LOG_PATH}'
        raise FileNotFoundError(error)
    remote_tmux_log = sftp_client.open(TMUX_LOG_PATH, 'r', bufsize=4096)

    # Start application (if required) and show tmux output in terminal
    if restart_application:
        remote_dir = f'/home/{ssh_client.username}/{LOCAL_PROJECT_DIRECTORY}'
        command = f'cd {remote_dir} && uv run --no-group dev {APPLICATION_FILE}'
        ssh_client.client.exec_command(f'tmux send-keys -t {TMUX_SESSION_NAME} "{command}" C-m')
        print(f'Application {APPLICATION_FILE} on {ssh_client.connection} has been started')

    # Set up user termination thread
    stop_event = threading.Event()

    def wait_for_enter() -> None:
        input()  # Waits until the user presses Enter
        print(f'{tmux_session_msg}')
        stop_event.set()

    input_thread = threading.Thread(target=wait_for_enter, daemon=True)
    input_thread.start()

    # tmux streaming
    print(f'{tmux_session_msg}')
    print('Press Enter to exit.')
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
    """Installs tmux on the remote Raspberry Pi (if not already installed)."""
    stdin, stdout, stderr = ssh_client.client.exec_command('which tmux')
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        print(f'Installing tmux on {ssh_client.connection}')
        stdin, stdout, stderr = ssh_client.client.exec_command('sudo apt install tmux -y')
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


def rpi_upload_app(ssh_client: SshClient) -> None:
    """Upload application files to RPI."""
    all_exclude_patterns = UPLOAD_EXCLUDES_FOLDERS + UPLOAD_EXCLUDES_FILES
    ssh_client.upload_recursive(LOCAL_PROJECT_DIRECTORY, all_exclude_patterns)


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
    args = parser.parse_args()

    with SshClientHandler(CONFIG_FILE) as ssh_client:
        if args.rpi_check_app:
            rpi_check_running_app(ssh_client, RPI_APPLICATION_PROCESS_NAME)
        if args.rpi_kill_app:
            proc_ids = rpi_check_running_app(ssh_client, RPI_APPLICATION_PROCESS_NAME, message_no_process=False)
            rpi_kill_app(ssh_client, RPI_APPLICATION_PROCESS_NAME, proc_ids)
        if args.rpi_run_app:
            proc_ids = rpi_check_running_app(ssh_client, RPI_APPLICATION_PROCESS_NAME, message_no_process=False)
            rpi_kill_app(ssh_client, RPI_APPLICATION_PROCESS_NAME, proc_ids, msg_no_kill=False)
            rpi_tmux(ssh_client, restart_application=True)
        if args.rpi_tmux:
            rpi_tmux(ssh_client)
        if args.rpi_copy_code:
            rpi_upload_app(ssh_client)
            proc_ids = rpi_check_running_app(ssh_client, RPI_APPLICATION_PROCESS_NAME, message_no_process=False)
            rpi_kill_app(ssh_client, RPI_APPLICATION_PROCESS_NAME, proc_ids, msg_no_kill=False)
            rpi_tmux(ssh_client, restart_application=True)


if __name__ == '__main__':
    main()
