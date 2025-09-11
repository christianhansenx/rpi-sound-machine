#!/usr/bin/env python3
"""Raspberry Pi installation script."""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from installer_tools import InstallerTools


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
        app_root_path = Path(__file__).resolve().parent
        print(f'Apply execute permission to sh files in: {app_root_path}')
        for filepath in app_root_path.rglob('*.sh'):
            if filepath.is_file():
                filepath.chmod(0o755)
        (app_root_path / 'install.py').chmod(0o755)
        (app_root_path / 'uninstall.py').chmod(0o755)

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

    def install_yq(self) -> None:
        if self.is_yq_installed():
            print('yq already installed. No installing...')
            return
        self.apt_get_update()
        print('Installing yq')
        self.run_command('sudo apt-get install yq -y')
        if not self.is_yq_installed():
            error = 'Could not install yq.'
            raise InstallError(error)

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
        """Install and start the systemd service."""
        self.restart_service()

    @staticmethod
    def install(installable_items: dict[str, callable], installs: list) -> None:
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
        'set_exec': installer.make_files_executable,
        'tmux': installer.install_tmux,
        'snap': installer.install_snap,
        'yq': installer.install_yq,
        'uv': installer.install_uv,
        'service': installer.install_service,
    }
    installable = list(installable_items.keys())

    installs = list(args.install) if args.install else list(installable)
    installs_ordered = installer.check_install_candidates(installable, installs)
    if not args.no_confirms:
        print()
        print(f'You are about to install{"" if args.install else " all"}: {" ".join(installs_ordered)}')
        answer = input('Are you sure you want to install? (y/N): ').strip().lower()
        if answer != 'y':
            print('Installation cancelled.')
            return
    print()
    installer.install(installable_items, installs_ordered)
    print()
    print('Success!')


if __name__ == '__main__':
    main()
