#!/bin/bash
# Update Script for Family Dashboard
# Safely updates the dashboard software
#
# Like install.sh, this locates itself rather than assuming a path, so the
# checkout can live anywhere and under any account name.

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(id -un)"
VENV="$APP_DIR/.venv"
PYTHON="$VENV/bin/python"

echo "======================================"
echo "Family Dashboard Update"
echo "======================================"
echo ""
echo "Dashboard location: $APP_DIR"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -x "$PYTHON" ]; then
    echo -e "${RED}No virtualenv at $VENV${NC}"
    echo "This install predates the virtualenv layout, or was never completed."
    echo "Run ./install.sh once - it is safe on an existing install and will"
    echo "keep your database and config."
    exit 1
fi

# Backups go to $HOME, deliberately outside the checkout, so `git pull` and a
# stray `git clean` can never touch them.
echo -e "${YELLOW}Creating backup...${NC}"
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$HOME/dashboard-backup-$STAMP.db"
if [ -f "$APP_DIR/backend/dashboard.db" ]; then
    cp "$APP_DIR/backend/dashboard.db" "$BACKUP_FILE"
    echo "Backup created: $BACKUP_FILE"
else
    echo -e "${YELLOW}No database yet - nothing to back up${NC}"
    BACKUP_FILE="(none)"
fi

# Photos live outside the database and are not in git, so they need their own copy.
if [ -d "$APP_DIR/backend/photos" ] && \
   [ -n "$(ls -A "$APP_DIR/backend/photos" 2>/dev/null)" ]; then
    PHOTO_BACKUP="$HOME/dashboard-photos-$STAMP.tar.gz"
    tar -czf "$PHOTO_BACKUP" -C "$APP_DIR/backend" photos
    echo "Photos backed up: $PHOTO_BACKUP"
fi
echo ""

# Stop services
echo -e "${YELLOW}Stopping services...${NC}"
sudo systemctl stop dashboard-backend || true
sudo systemctl stop dashboard-hardware || true
echo ""

# Pull latest changes (if using git)
if [ -d "$APP_DIR/.git" ]; then
    echo -e "${YELLOW}Updating from repository...${NC}"
    git -C "$APP_DIR" pull
    echo ""
else
    echo -e "${YELLOW}Not a git repository - skipping pull${NC}"
    echo "To update, manually copy new files to $APP_DIR"
    echo ""
fi

# Update Python dependencies
echo -e "${YELLOW}Updating Python dependencies...${NC}"
"$VENV/bin/pip" install -r "$APP_DIR/backend/requirements.txt" --upgrade
echo ""

# Run database migrations
# init_db() creates missing tables, adds columns introduced since this Pi was
# installed, backfills existing rows, and seeds new default settings.
# db.create_all() alone would NOT add the new columns to existing tables.
echo -e "${YELLOW}Checking database...${NC}"
cd "$APP_DIR/backend"
"$PYTHON" -c "from app import init_db; init_db()"
cd "$APP_DIR"
echo "Database schema updated"
echo ""

# Photo directory may be new since the last update.
mkdir -p "$APP_DIR/backend/photos"

# Re-render the systemd units. The same script install.sh uses, so an upgrade
# can never leave /etc out of step with the templates in config/.
echo -e "${YELLOW}Updating services...${NC}"
APP_DIR="$APP_DIR" RUN_USER="$RUN_USER" PYTHON="$PYTHON" \
    "$APP_DIR/config/install-services.sh"
echo ""

# Start services
echo -e "${YELLOW}Starting services...${NC}"
sudo systemctl start dashboard-backend || true
# Only if it was enabled: a non-Pi install leaves the hardware service off.
if systemctl is-enabled dashboard-hardware > /dev/null 2>&1; then
    sudo systemctl start dashboard-hardware || true
fi
echo ""

# Check service status
echo -e "${YELLOW}Checking service status...${NC}"
sleep 3

BACKEND_STATUS=$(systemctl is-active dashboard-backend || echo "failed")
if [ "$BACKEND_STATUS" == "active" ]; then
    echo -e "${GREEN}✓ Backend service is running${NC}"
else
    echo -e "${RED}✗ Backend service failed to start${NC}"
    echo "Check logs: sudo journalctl -u dashboard-backend -n 50"
fi

if systemctl is-enabled dashboard-hardware > /dev/null 2>&1; then
    HARDWARE_STATUS=$(systemctl is-active dashboard-hardware || echo "failed")
    if [ "$HARDWARE_STATUS" == "active" ]; then
        echo -e "${GREEN}✓ Hardware service is running${NC}"
    else
        echo -e "${RED}✗ Hardware service failed to start${NC}"
        echo "Check logs: sudo journalctl -u dashboard-hardware -n 50"
    fi
fi

echo ""
echo -e "${GREEN}======================================"
echo "Update Complete!"
echo "======================================${NC}"
echo ""
echo "Dashboard version: $(git -C "$APP_DIR" describe --tags 2>/dev/null \
    || git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "Backup saved: $BACKUP_FILE"
echo ""
if [ -f "$BACKUP_FILE" ]; then
    echo "To restore from backup if needed:"
    echo "  cp $BACKUP_FILE $APP_DIR/backend/dashboard.db"
    echo "  sudo systemctl restart dashboard-backend"
    echo ""
fi
