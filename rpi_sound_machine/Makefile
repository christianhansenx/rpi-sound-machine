.PHONY: no_arguments install check stop-app stop start restart run kill-tmux reboot

no_arguments:
	@echo "Missing argument. Arguments: install | check | stop-app | stop | start | restart | run | kill-tmux | reboot"

install:
	@echo "Installing applications and restarting application service."
	@python cli.py -y -i --restart-service

check:
	python cli.py --check

stop-app:
	python cli.py --stop-application

stop:
	python cli.py --stop-service

start:
	python cli.py --start-service

restart:
	python cli.py --restart-service

run:
	python cli.py --run

tmux:
	python cli.py --tmux

kill-tmux:
	python cli.py --kill-tmux

reboot:
	@echo "Rebooting device."
	@sudo reboot
