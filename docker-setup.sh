#!/usr/bin/env bash
# Helper script to set up and manage the Airflow Docker Compose environment.
# Based on the official Airflow Docker Compose guide:
# https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

# ── Create required directories ───────────────────────────────────────────────
info "Creating required directories: dags/ logs/ plugins/ config/"
mkdir -p ./dags ./logs ./plugins ./config

CMD="${1:-help}"

case "$CMD" in
  init)
    info "Building custom Docker image..."
    docker compose build

    info "Initialising the Airflow database..."
    docker compose up airflow-init

    info "Done! Run './docker-setup.sh up' to start Airflow."
    ;;

  up)
    info "Starting Airflow (detached)..."
    docker compose up -d
    info "Airflow UI available at http://localhost:8080  (login: airflow / airflow)"
    ;;

  down)
    info "Stopping Airflow..."
    docker compose down
    ;;

  reset)
    warn "This will remove ALL containers, volumes, and database data."
    read -r -p "Are you sure? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { warn "Aborted."; exit 0; }
    docker compose down --volumes --remove-orphans
    info "Environment reset. Run './docker-setup.sh init' to start fresh."
    ;;

  build)
    info "Rebuilding custom Docker image..."
    docker compose build
    ;;

  logs)
    docker compose logs -f
    ;;

  ps)
    docker compose ps
    ;;

  help|*)
    echo ""
    echo "Usage: ./docker-setup.sh <command>"
    echo ""
    echo "Commands:"
    echo "  init    Build the image and initialise the database (first-time setup)"
    echo "  up      Start all Airflow services in the background"
    echo "  down    Stop all Airflow services"
    echo "  build   Rebuild the custom Docker image"
    echo "  logs    Tail logs from all services"
    echo "  ps      Show container status"
    echo "  reset   Destroy all containers and volumes (clean slate)"
    echo ""
    ;;
esac
