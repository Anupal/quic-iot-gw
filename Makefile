# Makefile

build-pip:
	echo "Building PIP package"
	pip install -e .

build-qig-image:
	echo "Building QIG image."
	docker build -t qig -f extras/qig.Dockerfile .

start-sim-qig:
	echo "Starting QIG docker-compose simulation"
	docker compose -f docker-compose.simulation.yaml up -d

stop-sim-qig:
	echo "Stopping QIG docker-compose simulation"
	docker compose -f docker-compose.simulation.yaml down

start-sim-tig:
	echo "Starting TIG docker-compose simulation"
	docker compose -f docker-compose.simulation-tls.yaml up -d

stop-sim-tig:
	echo "Stopping TIG docker-compose simulation"
	docker compose -f docker-compose.simulation-tls.yaml down