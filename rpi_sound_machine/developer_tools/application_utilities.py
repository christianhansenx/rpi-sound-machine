#!/usr/bin/env python3
"""Raspberry Pi device tool."""
import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from utilities_tools import ApplicationProcess


def application_process_commands(args: argparse.Namespace, application_process: ApplicationProcess) -> None:
    if args.check:
        application_process.check()
    if args.stop_application:
        application_process.stop_application()
    if args.tmux:
        application_process.tmux()
    if args.kill_tmux:
        application_process.kill_tmux_session()
    if args.run:
        application_process.start_application_in_tmux_session()
    if args.stop_service:
        application_process.remove_service()
    if args.start_service:
        application_process.start_service()
    if args.restart_service:
        application_process.restart_service()


def main() -> None:
    """Call functions depending on script arguments.

    Raises:
        RuntimeError: if no argument were provided for the script.

    """
    print(f'UTC time: {datetime.now(tz=ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Python version: {sys.version_info.major}.{sys.version_info.minor}')

    parser = argparse.ArgumentParser(description='Raspberry Pi Application Utilities.')
    parser.add_argument(
        '--check',
        action='store_true',
        help='Printing application application info.',
    )
    parser.add_argument(
        '--stop-application',
        action='store_true',
        help='Stopping running application process and its system service.',
    )
    parser.add_argument(
        '--tmux',
        action='store_true',
        help='Open tmux session.',
    )
    parser.add_argument(
        '--kill-tmux',
        action='store_true',
        help='Killing application tmux session.',
    )
    parser.add_argument(
        '--run',
        action='store_true',
        help='Start application in tmux session. For developing purpose.',
    )
    parser.add_argument(
        '--stop-service',
        action='store_true',
        help='Removing application system service.',
    )
    parser.add_argument(
        '--start-service',
        action='store_true',
        help='Starting system service of application.',
    )
    parser.add_argument(
        '--restart-service',
        action='store_true',
        help='Restarting system service of application.',
    )

    if len(sys.argv) == 1:
        error = 'No arguments provided.'
        raise RuntimeError(error)

    args = parser.parse_args()
    application_process = ApplicationProcess()
    application_process_commands(args, application_process)
    print()


if __name__ == '__main__':
    main()
