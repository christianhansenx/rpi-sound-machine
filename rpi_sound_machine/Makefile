.PHONY: no_arguments install process-id stop kill-tmux restart-service run reboot

no_arguments:
	@echo "Missing argument. Arguments: install | process-id | stop | kill-tmux | restart-service | run | reboot"

install:
	@echo "Installing applications and restarting application service."
	@python device_tool.py -y -i --stop-application --restart-service

process-id:
	python device_tool.py --get-application-process-ids

stop:
	python device_tool.py --stop-application

kill-tmux:
	python device_tool.py --kill-tmux

restart-service:
	python device_tool.py --restart-service

run:
	python device_tool.py --run-application

reboot:
	@echo "Rebooting device."
	@sudo reboot
