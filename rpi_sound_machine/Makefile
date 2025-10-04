INSTALLATION_TARGET =  # To be assigned with make command, e.g: make install INSTALLATION_TARGET="tmux"
.PHONY: no_arguments install uninstall check stop-app stop-service start-service start restart run kill-tmux reboot

no_arguments:
	@echo "Missing argument. Arguments: install | check | stop-app | stop-service | restart | reboot"

install:
	sudo apt-get update
	@echo
	sudo apt-get upgrade -y
	@echo
	sudo apt-get install -y
	@echo
	sudo apt-get install tmux -y
	@echo
	sudo apt install snapd -y
	@echo
	sudo snap install snapd
	@echo
	sudo snap install astral-uv --classic

uninstall:
	python developer_tools/application_utilities.py --stop-application
	python developer_tools/application_utilities.py --stop-service
	@echo
	tmux kill-server || true
	@echo
	sudo apt-get remove -y tmux
	@echo
	sudo snap remove astral-uv || true
	@echo
	sudo apt-get purge snapd -y

check:
	python developer_tools/application_utilities.py --check

stop-app:
	python developer_tools/application_utilities.py --stop-application

stop-service:
	python developer_tools/application_utilities.py --stop-service

start-service:
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
