"""Raspberry Pi device tool."""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from device_tool_box import InstallerTools, settings


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
        permissions of all .sh files to be executable.
        """
        app_root_path = Path(__file__).resolve().parent
        print(f'Apply execute permission to sh files in: {app_root_path}')
        for filepath in app_root_path.rglob('*.sh'):
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

    @staticmethod
    def install(installable_items: dict[str, callable], installs: list) -> None:
        for item, func in installable_items.items():
            if item in installs:
                func()


def main() -> None:
    """Call functions depending on script arguments.

    Raises:
        RuntimeError: if no argument were provided for the script.

    """
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
        '--make-settings-file',
        action='store_true',
        help='Printing settings from setting file.',
    )
    parser.add_argument(
        '--install',
        nargs='*',  # Accepts zero or more arguments
        help='A list of items to install (e.g. tmux uv snap).',
    )
    parser.add_argument(
        '--skip-apt-get-update',
        action='store_true',
        help='Will skip "sudo apt-get update" during installing of applications.',
    )

    if len(sys.argv) == 1:
        error = 'No arguments provided.'
        raise RuntimeError(error)

    args = parser.parse_args()
    if args.make_settings_file:
        settings.create_make_include_file()

    if args.install is not None:
        installer = Installer(skip_apt_get_update=args.skip_apt_get_update)
        installable_items = {
            'set_exec': installer.make_files_executable,
            'tmux': installer.install_tmux,
            'snap': installer.install_snap,
            'uv': installer.install_uv,
            'service': installer.restart_service,
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
        if args.restart_service:
            installer.restart_service()
    print()


if __name__ == '__main__':
    main()
