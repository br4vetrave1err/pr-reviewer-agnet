# PR Review Agent — developer commands (docker compose wrapper).
# Usage: make <target>   (default target: help)

.PHONY: help up start logs logs-app logs-ngrok down restart rebuild ps status \
        tunnel test bootstrap clean

DOCKER := docker compose

help:
	@echo "PR Review Agent commands:"
	@echo "  make up         build images and start the stack (detached)"
	@echo "  make start      start the stack without rebuilding"
	@echo "  make logs       tail logs from all services"
	@echo "  make logs-app   tail app logs"
	@echo "  make logs-ngrok tail ngrok logs"
	@echo "  make down       stop and remove containers"
	@echo "  make restart    restart the stack"
	@echo "  make rebuild    rebuild images and force-recreate containers"
	@echo "  make ps         show container status"
	@echo "  make tunnel     print the current ngrok public URL"
	@echo "  make test       run the pytest suite"
	@echo "  make bootstrap  create .env and config.yaml from examples if missing"
	@echo "  make clean      stop and remove containers + volumes"

up:
	$(DOCKER) up -d --build

start:
	$(DOCKER) up -d

logs:
	$(DOCKER) logs -f --tail 100

logs-app:
	$(DOCKER) logs -f --tail 100 app

logs-ngrok:
	$(DOCKER) logs -f --tail 100 ngrok

down:
	$(DOCKER) down

restart:
	$(DOCKER) restart

rebuild:
	$(DOCKER) up -d --build --force-recreate

ps:
	$(DOCKER) ps

status:
	$(DOCKER) ps

tunnel:
	$(DOCKER) exec -T app python -c "import urllib.request,json;print([t['public_url'] for t in json.load(urllib.request.urlopen('http://ngrok:4040/api/tunnels',timeout=5))['tunnels']])"

test:
	python -m pytest

bootstrap:
	if not exist ".env" copy ".env.example" ".env"
	if not exist "config.yaml" copy "config.yaml.example" "config.yaml"
	@echo "bootstrap: .env and config.yaml ready (fill in real secrets before make up)"

clean:
	$(DOCKER) down -v --remove-orphans
