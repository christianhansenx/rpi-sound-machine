.PHONY: no_arguments install process-id stop kill-tmux restart-service run reboot

no_arguments:
	@echo "Missing argument. Arguments: install | process-id | stop | kill-tmux | restart-service | run | reboot"

install:
	@echo "Installing applications and restarting application service."
	@python cli.py -y -i --stop-application --restart-service

process-id:
	python cli.py --get-application-process-ids

stop:
	python cli.py --stop-application

kill-tmux:
	python cli.py --kill-tmux

restart-service:
	python cli.py --restart-service

run:
	python cli.py --run-application

reboot:
	@echo "Rebooting device."
	@sudo reboot
