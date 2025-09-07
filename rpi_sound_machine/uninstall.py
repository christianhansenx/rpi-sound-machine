"""Raspberry Pi uninstallation script."""
import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from installer_tools import InstallerTools


class UninstallError(Exception):
    """Exception raised when an uninstallation process fails."""


class Uninstaller(InstallerTools):
    """Class uninstallation."""

    def __init__(self) -> None:
        """Initialize uninstaller tools."""
        super().__init__()

    def uninstall_tmux(self) -> None:
        if not self.is_tmux_installed():
            print('tmux not found. No uninstalling...')
            return
        print('Uninstalling tmux')
        self.run_command('tmux kill-server')
        self.run_command('sudo apt-get remove -y tmux')
        if self.is_tmux_installed():
            error = 'Could not uninstall tmux.'
            raise UninstallError(error)

    def uninstall_uv(self) -> None:
        if not self.is_uv_installed():
            print('uv not found. No uninstalling...')
            return
        print('Uninstalling uv')
        self.run_command('sudo snap remove astral-uv')
        if self.is_uv_installed():
            error = 'Could not uninstall uv.'
            raise UninstallError(error)

    @staticmethod
    def uninstall(installable_items: dict[str, callable], uninstalls: set) -> None:
        for item, func in installable_items.items():
            if item in uninstalls:
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
        help='User will not be asked to confirmation uninstallation.',
    )
    parser.add_argument(
        '-u',
        '--uninstall',
        nargs='*',  # Accepts zero or more arguments
        help='A list of items to uninstall (e.g. tmux uv snap).',
    )

    args = parser.parse_args()
    uninstaller = Uninstaller()
    installable_items = {
        'tmux': uninstaller.uninstall_tmux,
        'uv': uninstaller.uninstall_uv,
    }
    installable = set(installable_items.keys())

    if args.uninstall is None:
        print('No uninstallation targets specified. Use -u or --uninstall option to specify items to uninstall.')
        print(f'Possible items are: {" ".join(installable)}')
        print('All items are to be uninstalled if no items provided.')
        return

    uninstalls = set(args.uninstall) if args.uninstall else set(installable)
    uninstaller.check_install_candidates(uninstalls, installable)
    if not args.no_confirms and args.uninstall is not None:
        print()
        print(f'You are about to uninstall{"" if args.uninstall else " all"}: {" ".join(uninstalls)}')
        answer = input('Are you sure you want to uninstall? (y/N): ').strip().lower()
        if answer != 'y':
            print('Uninstallation cancelled.')
            return
    uninstaller.uninstall(installable_items, uninstalls)
    print('Success!')


if __name__ == '__main__':
    main()
