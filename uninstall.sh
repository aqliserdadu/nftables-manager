#!/bin/bash
# =============================================================================
# nftables Manager Uninstallation Script
# =============================================================================
# This script removes the nftables Manager installation
# 
# Usage: sudo ./uninstall.sh
# =============================================================================
set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration variables (must match install script)
APP_NAME="nftables-manager"
APP_USER="nftables-manager"
APP_DIR="/opt/nftables-manager"
SERVICE_NAME="nftables-manager"
SERVICE_PORT=5000

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run as root"
    exit 1
fi

print_status "Starting nftables Manager uninstallation..."

# Check if the application is installed
if [[ ! -d "$APP_DIR" ]]; then
    print_error "nftables Manager is not installed in $APP_DIR"
    exit 1
fi

# Stop and disable service
print_status "Stopping and disabling nftables Manager service..."
if systemctl is-active --quiet ${SERVICE_NAME}; then
    systemctl stop ${SERVICE_NAME}
fi

if systemctl is-enabled --quiet ${SERVICE_NAME}; then
    systemctl disable ${SERVICE_NAME}
fi

# Remove systemd service file
print_status "Removing systemd service..."
if [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]; then
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    systemctl daemon-reload
    print_status "Systemd service removed"
else
    print_warning "Service file not found"
fi

# Remove firewall rule for service port
print_status "Removing firewall rules..."
if command -v nft &> /dev/null; then
    # Check if rule exists and remove it
    if nft list ruleset | grep -q "dport $SERVICE_PORT"; then
        nft delete rule inet filter input tcp dport $SERVICE_PORT accept
        print_status "Removed firewall rule for port $SERVICE_PORT"
    else
        print_warning "Firewall rule for port $SERVICE_PORT not found"
    fi
    
    # Save rules
    nft list ruleset > /etc/nftables/ruleset
elif command -v iptables &> /dev/null; then
    # Check if rule exists and remove it
    if iptables -L INPUT | grep -q "dport $SERVICE_PORT"; then
        iptables -D INPUT -p tcp --dport $SERVICE_PORT -j ACCEPT
        print_status "Removed iptables rule for port $SERVICE_PORT"
    else
        print_warning "iptables rule for port $SERVICE_PORT not found"
    fi
    
    # Save rules
    iptables-save > /etc/iptables/rules.v4
else
    print_warning "No firewall tool found (nftables/iptables)"
fi

# Remove application user
print_status "Removing application user..."
if id "$APP_USER" &>/dev/null; then
    userdel $APP_USER
    print_status "User $APP_USER removed"
else
    print_warning "User $APP_USER not found"
fi

# Remove application directory
print_status "Removing application directory..."
if [[ -d "$APP_DIR" ]]; then
    rm -rf $APP_DIR
    print_status "Application directory $APP_DIR removed"
else
    print_warning "Application directory $APP_DIR not found"
fi

# Remove configuration directories
print_status "Removing configuration directories..."
if [[ -d "/etc/nftables.d/backups" ]]; then
    rm -rf /etc/nftables.d/backups
    print_status "Configuration directory /etc/nftables.d/backups removed"
else
    print_warning "Configuration directory /etc/nftables.d/backups not found"
fi

# Note: We don't remove /etc/nftables.conf as it might contain system-wide rules

# Check if nftables service should be stopped
print_status "Checking nftables service status..."
if systemctl is-active --quiet nftables; then
    print_warning "nftables service is still running. You may want to stop it if not needed."
fi

# Uninstallation complete
print_status "=================================================================="
print_status "nftables Manager Uninstallation Complete!"
print_status "=================================================================="
echo
print_status "What was removed:"
echo "  - Systemd service: ${SERVICE_NAME}"
echo "  - Application directory: $APP_DIR"
echo "  - Application user: $APP_USER"
echo "  - Configuration directory: /etc/nftables.d/backups"
echo "  - Firewall rule for port $SERVICE_PORT"
echo
print_warning "Note: The following were NOT removed:"
echo "  - nftables service and rules (/etc/nftables.conf)"
echo "  - Python packages and dependencies"
echo "  - System packages (python3, nftables, etc.)"
echo
print_status "To completely remove nftables from your system:"
echo "  sudo systemctl stop nftables"
echo "  sudo systemctl disable nftables"
echo "  sudo apt purge nftables  # or 'sudo yum remove nftables' for RedHat"
echo