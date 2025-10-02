.PHONY: no_arguments install check stop-app stop start restart run kill-tmux reboot

no_arguments:
	@echo "Missing argument. Arguments: install | check | stop-app | stop | start | restart | run | kill-tmux | reboot"

install:
	@echo "Installing applications and restarting application service."
	@python cli.py -y -i --restart-service

check:
	python developer_tools/application_utilities.py --check

stop-app:
	python developer_tools/application_utilities.py --stop-application

stop:
	python developer_tools/application_utilities.py --stop-service

start:
	python developer_tools/application_utilities.py --start-service

restart:
	python developer_tools/application_utilities.py --restart-service

run:
	python developer_tools/application_utilities.py --run

tmux:
	python developer_tools/application_utilities.py --tmux

kill-tmux:
	python developer_tools/application_utilities.py --kill-tmux

reboot:
	@echo "Rebooting device."
	@sudo reboot
