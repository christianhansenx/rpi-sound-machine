"""Raspberry Pi installation script."""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from installer_tools import (
    LOCAL_SERVICE_FILE,
    LOCAL_START_SCRIPT,
    SERVICE_NAME,
    SYSTEM_SERVICE_FILE,
    SYSTEM_START_SCRIPT,
    InstallerTools,
)


class InstallError(Exception):
    """Exception raised when an uninstallation process fails."""


class Installer(InstallerTools):
    """Class installation."""

    def __init__(self, *, skip_apt_get_update: bool = False) -> None:
        """Initialize installer tools."""
        super().__init__(skip_apt_get_update=skip_apt_get_update)

    @staticmethod
    def make_files_executable() -> None:
        """Make files executable.

        Traverses all directories from the current location and changes the
        permissions of all .sh files to be.
        """
        start_path = Path.cwd()
        print(f'Apply execute permission to sh files in: {start_path}')
        for filepath in start_path.rglob('*.sh'):
            if filepath.is_file():
                filepath.chmod(0o755)

    def install_tmux(self) -> None:
        if self.is_tmux_installed():
            print('tmux already installed. No installing...')
            return
        self.apt_get_update()
        print('Installing tmux')
        self.run_command('sudo apt-get install -y tmux')
        if not self.is_tmux_installed():
            error = 'Could not install tmux.'
            raise InstallError(error)

    def install_snap(self) -> None:
        if self.is_snap_installed():
            print('snap already installed. No installing...')
            return
        self.apt_get_update()
        print('Installing snap')
        self.run_command('sudo apt install snapd')
        self.run_command('sudo snap install snapd')
        if not self.is_snap_installed():
            error = 'Could not install uv.'
            raise InstallError(error)
        self.set_reboot_required()

    def install_uv(self) -> None:
        if self.is_uv_installed():
            print('uv already installed. No installing...')
            return
        self.apt_get_update()
        print('Installing uv')
        self.run_command('sudo snap install astral-uv --classic')
        if not self.is_uv_installed():
            error = 'Could not install uv.'
            raise InstallError(error)
        self.set_reboot_required()

    def install_service(self) -> None:
        """Install the systemd service."""
        service_changed = self.files_are_different(LOCAL_SERVICE_FILE, SYSTEM_SERVICE_FILE)
        script_changed = self.files_are_different(LOCAL_START_SCRIPT, SYSTEM_START_SCRIPT)

        if not service_changed and not script_changed:
            print('Service setup is already up to date. No changes needed.')
            return

        print('Service setup changes detected. Updating service setup.')

        # Stop the service before making changes
        self.run_command(f'sudo systemctl stop {SERVICE_NAME}', check=False)

        if service_changed:
            self.run_command(f'sudo cp {LOCAL_SERVICE_FILE} {SYSTEM_SERVICE_FILE}')

        if script_changed:
            self.run_command(f'sudo cp {LOCAL_START_SCRIPT} {SYSTEM_START_SCRIPT}')

        self.run_command('sudo systemctl daemon-reload')
        self.run_command(f'sudo systemctl enable {SERVICE_NAME}')
        self.run_command(f'sudo systemctl start {SERVICE_NAME}')
        self.set_reboot_required()

    @staticmethod
    def install(installable_items: dict[str, callable], installs: set) -> None:
        for item, func in installable_items.items():
            if item in installs:
                func()


def main() -> None:
    """Call functions depending on script arguments."""
    print(f'UTC time: {datetime.now(tz=ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Python version: {sys.version_info.major}.{sys.version_info.minor}')

    parser = argparse.ArgumentParser(description='Raspberry Pi Uninstaller.')
    parser.add_argument(
        '-y',
        '--no-confirms',
        action='store_true',
        help='User will not be asked to confirmation installation.',
    )
    parser.add_argument(
        '--skip-apt-get-update',
        action='store_true',
        help='Will skip "sudo apt-get update".',
    )
    parser.add_argument(
        '-i',
        '--install',
        nargs='*',  # Accepts zero or more arguments
        help='A list of items to install (e.g. tmux uv snap).',
    )

    args = parser.parse_args()
    installer = Installer(skip_apt_get_update=args.skip_apt_get_update)
    installable_items = {
        'tmux': installer.install_tmux,
        'snap': installer.install_snap,
        'uv': installer.install_uv,
    }
    installable = set(installable_items.keys())

    installs = set(args.install) if args.install else set(installable)
    installer.check_install_candidates(installs, installable)
    if not args.no_confirms:
        print()
        print(f'You are about to install{"" if args.install else " all"}: {" ".join(installs)}')
        answer = input('Are you sure you want to install? (y/N): ').strip().lower()
        if answer != 'y':
            print('Installation cancelled.')
            return
    print()
    installer.make_files_executable()
    installer.install(installable_items, installs)
    installer.install_service()
    print('Success!')


if __name__ == '__main__':
    main()
