#!/bin/bash

# =============================================================================
# nftables Manager Installation Script
# =============================================================================
# This script automates the installation of nftables Manager
# 
# Usage: sudo ./install.sh
# =============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration variables
APP_NAME="nftables-manager"
APP_USER="nftables-manager"
APP_DIR="/opt/nftables-manager"
SERVICE_NAME="nftables-manager"
SERVICE_PORT=5000
PYTHON_VERSION="3"

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

print_status "Starting nftables Manager installation..."

# Detect OS
if [[ -f /etc/debian_version ]] || [[ -f /etc/ubuntu_version ]]; then
    OS="debian"
    PACKAGE_MANAGER="apt"
elif [[ -f /etc/centos-release ]] || [[ -f /etc/redhat-release ]]; then
    OS="redhat"
    PACKAGE_MANAGER="yum"
else
    print_error "Unsupported operating system"
    exit 1
fi

print_status "Detected OS: $OS"

# Update system
print_status "Updating system packages..."
if [[ $OS == "debian" ]]; then
    apt update
    apt upgrade -y
else
    yum update -y
    yum upgrade -y
fi

# Install Python and dependencies
print_status "Installing Python and dependencies..."
if [[ $OS == "debian" ]]; then
    apt install -y python3 python3-pip python3-venv python3-dev
else
    yum install -y python3 python3-pip python3-devel
fi

# Install nftables
print_status "Installing nftables..."
if [[ $OS == "debian" ]]; then
    apt install -y nftables
else
    yum install -y nftables
fi

# Enable and start nftables service
print_status "Enabling nftables service..."
systemctl enable nftables
systemctl start nftables

# Create application user
print_status "Creating application user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d /opt -c "nftables Manager" $APP_USER
    print_status "Created user: $APP_USER"
else
    print_warning "User $APP_USER already exists"
fi

# Create application directory
print_status "Creating application directory..."
mkdir -p $APP_DIR
chown $APP_USER:$APP_USER $APP_DIR
chown $APP_USER:$APP_USER /opt

# Create configuration directories
print_status "Creating configuration directories..."
mkdir -p /etc/nftables.d/backups
chown $APP_USER:$APP_USER /etc/nftables.d

# Create empty nftables config if not exists
if [[ ! -f /etc/nftables.conf ]]; then
    print_status "Creating empty nftables.conf..."
    touch /etc/nftables.conf
fi
chown $APP_USER:$APP_USER /etc/nftables.conf

# Copy application files
print_status "Copying application files..."
cp -r . $APP_DIR/
chown -R $APP_USER:$APP_USER $APP_DIR

# Create virtual environment
print_status "Creating Python virtual environment..."
cd $APP_DIR
sudo -u $APP_USER python3 -m venv venv
sudo -u $APP_USER source venv/bin/activate
pip install -r requirements.txt

# Create systemd service file
print_status "Creating systemd service..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=nftables Manager Web Interface
After=network.target nftables.service

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable service
systemctl enable ${SERVICE_NAME}

# Open firewall port
print_status "Configuring firewall..."
if command -v nft &> /dev/null; then
    # Check if rule already exists
    if ! nft list ruleset | grep -q "dport $SERVICE_PORT"; then
        nft add rule inet filter input tcp dport $SERVICE_PORT accept
        print_status "Opened port $SERVICE_PORT in firewall"
    else
        print_warning "Port $SERVICE_PORT already open in firewall"
    fi
elif command -v iptables &> /dev/null; then
    # Check if rule already exists
    if ! iptables -L INPUT | grep -q "dport $SERVICE_PORT"; then
        iptables -A INPUT -p tcp --dport $SERVICE_PORT -j ACCEPT
        print_status "Opened port $SERVICE_PORT in firewall"
    else
        print_warning "Port $SERVICE_PORT already open in firewall"
    fi
fi

# Save firewall rules
if command -v nft &> /dev/null; then
    nft list ruleset > /etc/nftables/ruleset
elif command -v iptables &> /dev/null; then
    iptables-save > /etc/iptables/rules.v4
fi

# Start service
print_status "Starting nftables Manager service..."
systemctl start ${SERVICE_NAME}

# Check service status
if systemctl is-active --quiet ${SERVICE_NAME}; then
    print_status "nftables Manager service started successfully"
else
    print_error "Failed to start nftables Manager service"
    systemctl status ${SERVICE_NAME}
    exit 1
fi

# Get server IP
SERVER_IP=$(hostname -I | awk '{print $1}')
if [[ -z "$SERVER_IP" ]]; then
    SERVER_IP="localhost"
fi

# Installation complete
print_status "=================================================================="
print_status "nftables Manager Installation Complete!"
print_status "=================================================================="
echo
print_status "Service Status:"
systemctl status ${SERVICE_NAME} --no-pager -l
echo
print_status "Access URLs:"
echo "  Local: http://localhost:$SERVICE_PORT"
echo "  Network: http://$SERVER_IP:$SERVICE_PORT"
echo
print_status "Default Login:"
echo "  Username: admin"
echo "  Password: admin123"
echo
print_status "Post-Installation Steps:"
echo "1. Change the default password immediately"
echo "2. Configure your firewall rules through the web interface"
echo "3. Set up regular backups"
echo
print_status "Service Management:"
echo "  Start: systemctl start ${SERVICE_NAME}"
echo "  Stop: systemctl stop ${SERVICE_NAME}"
echo "  Restart: systemctl restart ${SERVICE_NAME}"
echo "  Status: systemctl status ${SERVICE_NAME}"
echo "  Logs: journalctl -u ${SERVICE_NAME} -f"
echo
print_status "Configuration Files:"
echo "  Application: $APP_DIR"
echo "  Database: $APP_DIR/firewall.db"
echo "  Config: /etc/nftables.conf"
echo "  Backups: /etc/nftables.d/backups/"
echo "  Logs: /var/log/syslog (journalctl -u ${SERVICE_NAME})"
echo
print_warning "IMPORTANT:"
print_warning "1. Change the default admin password immediately!"
print_warning "2. Make sure port $SERVICE_PORT is accessible from your network"
print_warning "3. Configure firewall rules according to your security requirements"
print_warning "4. Set up regular backups of your configuration"
echo

# Create requirements.txt file
cat > $APP_DIR/requirements.txt << EOF
Flask==2.3.3
Werkzeug==2.3.7