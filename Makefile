# Makefile

build-pip:
	echo "Building PIP package"
	pip install -e .

build-qig-image:
	echo "Building QIG image."
	docker build -t qig -f extras/qig.Dockerfile .

start-sim:
	echo "Starting docker-compose simulation"
	docker compose -f docker-compose.simulation.yaml up -d

stop-sim:
	echo "Stopping docker-compose simulation"
	docker compose -f docker-compose.simulation.yaml down