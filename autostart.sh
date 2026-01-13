#!/bin/bash
# ZeroCoder Autostart Manager
# Manages systemd user service for running ZeroCoder on system boot
#
# Usage:
#   ./autostart.sh          # Enable autostart
#   ./autostart.sh --remove # Disable and remove autostart

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="zerocoder"
SERVICE_FILE="$HOME/.config/systemd/user/${SERVICE_NAME}.service"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

create_service() {
    echo -e "${YELLOW}Creating ZeroCoder systemd service...${NC}"

    # Create systemd user directory if it doesn't exist
    mkdir -p "$HOME/.config/systemd/user"

    # Create the service file
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=ZeroCoder Autonomous Coding Agent
After=network.target docker.service

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${SCRIPT_DIR}/start-app.sh
Restart=on-failure
RestartSec=10
Environment=PATH=/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin

[Install]
WantedBy=default.target
EOF

    # Reload systemd user daemon
    systemctl --user daemon-reload

    # Enable the service to start on boot
    systemctl --user enable "$SERVICE_NAME"

    # Enable lingering so user services run without login
    loginctl enable-linger "$USER"

    echo -e "${GREEN}ZeroCoder autostart enabled!${NC}"
    echo ""
    echo "Commands:"
    echo "  Start now:      systemctl --user start $SERVICE_NAME"
    echo "  Stop:           systemctl --user stop $SERVICE_NAME"
    echo "  Status:         systemctl --user status $SERVICE_NAME"
    echo "  Logs:           journalctl --user -u $SERVICE_NAME -f"
    echo "  Remove:         ./autostart.sh --remove"
}

remove_service() {
    echo -e "${YELLOW}Removing ZeroCoder autostart...${NC}"

    # Stop the service if running
    systemctl --user stop "$SERVICE_NAME" 2>/dev/null

    # Disable the service
    systemctl --user disable "$SERVICE_NAME" 2>/dev/null

    # Remove the service file
    rm -f "$SERVICE_FILE"

    # Reload systemd
    systemctl --user daemon-reload

    echo -e "${GREEN}ZeroCoder autostart removed.${NC}"
}

# Main
case "$1" in
    --remove|-r)
        remove_service
        ;;
    --help|-h)
        echo "ZeroCoder Autostart Manager"
        echo ""
        echo "Usage:"
        echo "  ./autostart.sh          Enable autostart on boot"
        echo "  ./autostart.sh --remove Disable and remove autostart"
        echo "  ./autostart.sh --help   Show this help"
        ;;
    *)
        create_service
        ;;
esac
