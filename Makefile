# RoadMind AI - Docker Commands

# Start everything
up:
	docker compose up -d --build

# Stop everything
down:
	docker compose down

# Restart everything
restart:
	docker compose restart

# View all logs
logs:
	docker compose logs -f

# View backend logs only
logs-backend:
	docker compose logs backend -f

# View frontend logs only
logs-frontend:
	docker compose logs frontend -f

# Rebuild and restart
rebuild:
	docker compose down
	docker compose up -d --build

# Check running containers
status:
	docker compose ps

# Remove all containers and volumes
clean:
	docker compose down -v
	docker system prune -f

# Open backend shell
shell-backend:
	docker compose exec backend bash

# Open frontend shell
shell-frontend:
	docker compose exec frontend sh

# Seed RAG database
seed-rag:
	docker compose exec backend \
	python rag/seed_data.py

.PHONY: up down restart logs logs-backend \
        logs-frontend rebuild status clean \
        shell-backend shell-frontend seed-rag
