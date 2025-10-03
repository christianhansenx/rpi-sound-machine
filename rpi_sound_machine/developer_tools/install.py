#!/usr/bin/env python3
"""Raspberry Pi device tool."""
import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from utilities_tools import InstallerTools, run_command


class InstallError(Exception):
    """Exception raised when an installation process fails."""


class Installer(InstallerTools):
    """Class installation."""

    def __init__(self, *, skip_apt_get_update: bool = False) -> None:
        """Initialize installer tools."""
        super().__init__(skip_apt_get_update=skip_apt_get_update)

    def install_tmux(self) -> None:
        if self.is_tmux_installed():
            print('tmux already installed. No installing...')
            return
        self.apt_get_update()
        print('Installing tmux')
        run_command('sudo apt-get install -y tmux')
        if not self.is_tmux_installed():
            error = 'Could not install tmux.'
            raise InstallError(error)

    def install_snap(self) -> None:
        if self.is_snap_installed():
            print('snap already installed. No installing...')
            return
        self.apt_get_update()
        print('Installing snap')
        run_command('sudo apt install snapd')
        run_command('sudo snap install snapd')
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
        run_command('sudo snap install astral-uv --classic')
        if not self.is_uv_installed():
            error = 'Could not install uv.'
            raise InstallError(error)
        self.set_reboot_required()

    @staticmethod
    def install(installable_items: dict[str, callable], installs: list) -> None:
        for item, func in installable_items.items():
            if item in installs:
                func()


def main() -> None:
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
        '-i',
        '--install',
        nargs='*',  # Accepts zero or more arguments
        help='A list of items to install (e.g. tmux uv snap).',
    )
    parser.add_argument(
        '--skip-apt-get-update',
        action='store_true',
        help='Will skip "sudo apt-get update" during installing of applications.',
    )

    args = parser.parse_args()
    installer = Installer(skip_apt_get_update=args.skip_apt_get_update)
    installable_items = {
        'tmux': installer.install_tmux,
        'snap': installer.install_snap,
        'uv': installer.install_uv,
    }
    installable = list(installable_items.keys())

    if len(sys.argv) == 1 or args.install is None:
        print()
        print('No installation targets specified. Use -i or --install option to specify targets to be installed.')
        print(f'Possible targets are: {" ".join(installable_items)}')
        print('All items are to be installed if no targets provided.')
        return

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


if __name__ == '__main__':
    main()
