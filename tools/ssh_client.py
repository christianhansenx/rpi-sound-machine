"""SSH Client."""
import getpass
import types
from contextlib import suppress
from pathlib import Path, PurePosixPath

import paramiko
import yaml


class SshClient:
    """SSH Client containing SSH connection client and some configuration values."""

    def __init__(self, client: paramiko.SSHClient, config: dict[str,str]) -> None:
        """Set client to a paramiko ssh client."""
        self._client = client
        self._username = config['username']
        self._connection = f'{config['username']}@{config['hostname']}'
        self._sftp = None

    @property
    def client(self) -> paramiko.SSHClient:
        """Provide ssh client."""
        return self._client

    @property
    def username(self) -> str:
        """Provide ssh connection username."""
        return self._username

    @property
    def connection(self) -> str:
        """Provide ssh connection name (username@hostname)."""
        return self._connection

    def upload_recursive(self, root_directory: str, exclude_patterns: list[str] | None) -> None:
        """Upload files to remote device like rsync."""
        exclude = exclude_patterns or []
        script_dir = Path(__file__).parent
        local_dir = (script_dir / '..' / root_directory).resolve()

        # Use PurePosixPath for remote paths
        remote_dir = PurePosixPath(f'/home/{self.username}') / root_directory

        print(f'Syncing {root_directory} to {self.connection}:{remote_dir}')
        self._sftp = self.client.open_sftp()

        def _upload_dir(local_path: Path, remote_path: PurePosixPath) -> None:
            with suppress(OSError):
                self._sftp.mkdir(str(remote_path))
            for item in local_path.iterdir():
                local_item = item
                remote_item = remote_path / item.name
                if self._is_excluded(local_item, exclude):
                    continue
                if local_item.is_dir():
                    _upload_dir(local_item, remote_item)
                else:
                    _upload_file_if_newer(local_item, remote_item)

        def _upload_file_if_newer(local_file: Path, remote_file: PurePosixPath) -> None:
            local_mtime = local_file.stat().st_mtime
            try:
                remote_attr = self._sftp.stat(str(remote_file))
                remote_mtime = remote_attr.st_mtime
                if local_mtime > remote_mtime:  # Local file is newer
                    print(f'Updating remote file: {remote_file}')
                    self._sftp.put(str(local_file), str(remote_file))
            except OSError:
                # File does not exist remotely, so upload it
                print(f'Uploading new file: {remote_file}')
                self._sftp.put(str(local_file), str(remote_file))

        self._delete_extra_remote_files(local_dir, remote_dir, exclude)
        _upload_dir(local_dir, remote_dir)
        self._sftp.close()

    @staticmethod
    def _is_excluded(path: Path, exclude: list[str]) -> bool:
        return any(
            pattern in str(path) or path.name == pattern or str(path).endswith(pattern)
            for pattern in exclude
        )

    def _delete_extra_remote_files(self, local_path: Path, remote_path: PurePosixPath, exclude: list[str]) -> None:

        try:
            for item in self._sftp.listdir(str(remote_path)):
                remote_item = remote_path / item
                local_item = local_path / item

                if self._is_excluded(remote_item, exclude):
                    continue

                try:
                    attr = self._sftp.stat(str(remote_item))
                    if str(attr.st_mode).startswith('16877'):  # Directory
                        if not local_item.is_dir():
                            self._remove_remote_dir(remote_item)
                        else:
                            self._delete_extra_remote_files(local_path,remote_item, exclude)
                    elif not local_item.exists():
                        self._sftp.remove(str(remote_item))
                except OSError:
                    pass
        except OSError:
            pass

    def _remove_remote_dir(self, path: PurePosixPath) -> None:
        for item in self._sftp.listdir(str(path)):
            remote_item = path / item
            attr = self._sftp.stat(str(remote_item))
            if str(attr.st_mode).startswith('16877'):  # Directory
                self._remove_remote_dir(remote_item)
            else:
                self._sftp.remove(str(remote_item))
        self._sftp.rmdir(str(path))


class SshClientHandler:
    """Context manager for ssh client."""

    def __init__(self, config_file: Path) -> None:
        """Get SSH connection configurations from file."""
        self._config = self._load_or_create_config(config_file)
        self._client = None

    def __enter__(self) -> SshClient:
        """Open a SSH connection."""
        print(f'Create SSH connection to {self._config['username']}@{self._config['hostname']}')
        print()
        client = paramiko.SSHClient()

        # Linting: S507 Paramiko call with policy set to automatically trust the unknown host key
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # noqa: S507

        client.connect(
            hostname=self._config['hostname'],
            username=self._config['username'],
            password=self._config['password'],
        )
        self._client = SshClient(client, self._config)
        return self._client

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
       """Close SSH connection."""
       if self._client:
            self._client.client.close()
            print()
            print('SSH connection is closed')


    @staticmethod
    def _load_or_create_config(config_file: Path) -> None:
        if Path.exists(config_file):
            with Path.open(config_file) as file:
                config = yaml.safe_load(file) or {}
        else:
            config = {}
            print(f'Configuration file {config_file} has not been created yet. Please enter the details:')
            print('Please enter the details:')
            config['hostname'] = input(' Raspberry Pi hostname: ').strip()
            config['username'] = input(' Raspberry Pi username: ').strip()
            config['password'] = getpass.getpass(' Password: ')
            with Path.open(config_file, 'w') as file:
                yaml.safe_dump(config, file)
            print(f'Configuration saved to {config_file}')
        print(f'Raspberry Pi hostname: {config['hostname']}')
        print(f'Raspberry Pi username: {config['username']}')
        return config
