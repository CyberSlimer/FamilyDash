#!/bin/bash
# Update Script for Family Dashboard
# Safely updates the dashboard software

set -e

echo "======================================"
echo "Family Dashboard Update"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Backup database before updating
echo -e "${YELLOW}Creating backup...${NC}"
BACKUP_FILE="$HOME/dashboard-backup-$(date +%Y%m%d-%H%M%S).db"
cp $HOME/family-dashboard/backend/dashboard.db "$BACKUP_FILE"
echo "Backup created: $BACKUP_FILE"
echo ""

# Stop services
echo -e "${YELLOW}Stopping services...${NC}"
sudo systemctl stop dashboard-backend || true
sudo systemctl stop dashboard-hardware || true
echo ""

# Pull latest changes (if using git)
if [ -d "$HOME/family-dashboard/.git" ]; then
    echo -e "${YELLOW}Updating from repository...${NC}"
    cd $HOME/family-dashboard
    git pull
    echo ""
else
    echo -e "${YELLOW}Not a git repository - skipping pull${NC}"
    echo "To update, manually copy new files to /home/pi/family-dashboard"
    echo ""
fi

# Update Python dependencies
echo -e "${YELLOW}Updating Python dependencies...${NC}"
cd $HOME/family-dashboard/backend
pip3 install -r requirements.txt --upgrade --break-system-packages
echo ""

# Run database migrations (if any)
echo -e "${YELLOW}Checking database...${NC}"
python3 << 'EOF'
from app import app, db
with app.app_context():
    db.create_all()
    print("Database schema updated")
EOF
echo ""

# Update systemd services if changed
echo -e "${YELLOW}Updating services...${NC}"
sudo cp $HOME/family-dashboard/config/dashboard-backend.service /etc/systemd/system/
sudo cp $HOME/family-dashboard/config/dashboard-hardware.service /etc/systemd/system/
sudo systemctl daemon-reload
echo ""

# Start services
echo -e "${YELLOW}Starting services...${NC}"
sudo systemctl start dashboard-backend
sudo systemctl start dashboard-hardware
echo ""

# Check service status
echo -e "${YELLOW}Checking service status...${NC}"
sleep 2

BACKEND_STATUS=$(sudo systemctl is-active dashboard-backend || echo "failed")
HARDWARE_STATUS=$(sudo systemctl is-active dashboard-hardware || echo "failed")

if [ "$BACKEND_STATUS" == "active" ]; then
    echo -e "${GREEN}✓ Backend service is running${NC}"
else
    echo -e "${RED}✗ Backend service failed to start${NC}"
    echo "Check logs: sudo journalctl -u dashboard-backend -n 50"
fi

if [ "$HARDWARE_STATUS" == "active" ]; then
    echo -e "${GREEN}✓ Hardware service is running${NC}"
else
    echo -e "${RED}✗ Hardware service failed to start${NC}"
    echo "Check logs: sudo journalctl -u dashboard-hardware -n 50"
fi

echo ""
echo -e "${GREEN}======================================"
echo "Update Complete!"
echo "======================================${NC}"
echo ""
echo "Dashboard version: $(cd $HOME/family-dashboard && git describe --tags 2>/dev/null || echo 'unknown')"
echo "Backup saved: $BACKUP_FILE"
echo ""
echo "To restore from backup if needed:"
echo "  cp $BACKUP_FILE $HOME/family-dashboard/backend/dashboard.db"
echo "  sudo systemctl restart dashboard-backend"
echo ""
