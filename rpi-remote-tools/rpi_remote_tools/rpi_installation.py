"""RPI Installation."""
from pydantic import BaseModel, Field

from .ssh_client import SshClient, SshClientHandler


class RpiInstallationError(Exception):
    """Could do installation on RPI."""


class RpiRemoteConfig(BaseModel):
    """Pydantic model for configuration."""

    local_project_directory: str = Field(..., description='The local project directory to sync to the RPI.')
    application_file: str = Field(..., description='The main application file to run on the RPI.')
    tmux_session_name: str = Field(..., description='The name of the tmux session to use on the RPI.')
    tmux_log_file_path: str = Field(..., description='The path on RPI for tmux logging.')


def rpi_installation(ssh_client: SshClient, config: RpiRemoteConfig) -> None:
    """Prepare RPI for running application as a service.

    Raises:
        RpiInstallationError: If installation fails.

    """
    print(f'Preparing RPI on {ssh_client.connection}')

    _install_tmux(ssh_client)

    service_name = config.tmux_session_name
    service_file_name = f'{service_name}.service'
    start_script_path = f'/usr/local/bin/start_{service_name}.sh'

    # Stop and disable the service if it exists
    ssh_client.client.exec_command(f"sudo systemctl stop {service_file_name}")
    ssh_client.client.exec_command(f"sudo systemctl disable {service_file_name}")

    # Create the start script
    start_script_content = f"""\
#!/bin/bash
tmux kill-session -t {service_name} 2>/dev/null
rm {config.tmux_log_file_path} 2>/dev/null
tmux new-session -d -s {service_name}
tmux pipe-pane -t {service_name}:0.0 -o "cat >> {config.tmux_log_file_path}"
tmux send-keys -t {service_name} 'cd /home/{ssh_client.username}/{config.local_project_directory} && uv run --quiet --no-group dev {config.application_file}' C-m
"""

    command = f"echo '{start_script_content}' | sudo tee {start_script_path} > /dev/null"
    _stdin, stdout, stderr = ssh_client.client.exec_command(command)
    if stdout.channel.recv_exit_status() != 0:
        raise RpiInstallationError(f"Failed to create start script: {stderr.read().decode()}")

    command = f"sudo chmod +x {start_script_path}"
    _stdin, stdout, stderr = ssh_client.client.exec_command(command)
    if stdout.channel.recv_exit_status() != 0:
        raise RpiInstallationError(f"Failed to make start script executable: {stderr.read().decode()}")

    # Create the service file
    service_file_content = f"""\
[Unit]
Description={service_name} service
After=network.target
[Service]
Type=forking
User={ssh_client.username}
ExecStart={start_script_path}
ExecStop=/usr/bin/tmux kill-session -t {service_name}
[Install]
WantedBy=multi-user.target
"""
    command = f"echo '{service_file_content}' | sudo tee /etc/systemd/system/{service_file_name} > /dev/null"
    _stdin, stdout, stderr = ssh_client.client.exec_command(command)
    if stdout.channel.recv_exit_status() != 0:
        raise RpiInstallationError(f"Failed to create service file: {stderr.read().decode()}")

    # Reload, enable and start the service
    commands = [
        "sudo systemctl daemon-reload",
        f"sudo systemctl enable {service_file_name}",
        f"sudo systemctl start {service_file_name}",
    ]
    for cmd in commands:
        print(f"Executing: {cmd}")
        _stdin, stdout, stderr = ssh_client.client.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            raise RpiInstallationError(f"Failed to execute '{cmd}': {stderr.read().decode()}")
        print(f"Successfully executed '{cmd}'")

    print(f' - Service "{service_name}" is set up and running.')
    print()


def _install_tmux(ssh_client: SshClient) -> None:
    """Installs tmux on the remote Raspberry Pi (if not already installed).

    Raises:
        RpiInstallationError: If installation fails.

    """
    _stdin, stdout, stderr = ssh_client.client.exec_command('which tmux')
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        print(f'- Installing tmux on {ssh_client.connection}')
        _stdin, stdout, stderr = ssh_client.client.exec_command('sudo apt install tmux -y')
        stdout_output = stdout.read().decode()
        stderr_output = stderr.read().decode()
        for line in stdout_output.splitlines():
            print(f'\t{line}')
        for line in stderr_output.splitlines():
            print(f'\t{line}')
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            error = f'tmux installation failed on {ssh_client.connection}:\n{stderr_output.strip()}'
            raise RpiInstallationError(error)
