#!/bin/bash
# Script instalasi untuk nftables Manager
# Jalankan sebagai root: sudo ./install.sh
set -e  # Exit immediately if a command exits with a non-zero status.
# Warna untuk output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
# Fungsi untuk mencetak pesan dengan warna
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}
print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}
print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}
# Cek apakah script dijalankan sebagai root
if [[ $EUID -ne 0 ]]; then
   print_error "Script ini harus dijalankan sebagai root"
   exit 1
fi
print_info "Memulai instalasi nftables Manager..."
# Update sistem
print_info "Update sistem..."
apt-get update
apt-get upgrade -y
# Install dependensi
print_info "Menginstall dependensi..."
apt-get install -y python3 python3-pip python3-venv nftables sqlite3 supervisor
# Buat direktori aplikasi
APP_DIR="/opt/nftables-manager"
print_info "Membuat direktori aplikasi di $APP_DIR..."
mkdir -p $APP_DIR
# Buat direktori untuk database dan log
mkdir -p /var/lib/nftables_manager
mkdir -p /var/log/nftables_manager
# Buat direktori untuk konfigurasi nftables
mkdir -p /etc/nftables.d
mkdir -p /etc/nftables.d/backups
# Salin file aplikasi (asumsikan file app.py ada di direktori yang sama)
print_info "Menyalin file aplikasi..."
cp -r . $APP_DIR/
chmod 640 $APP_DIR/app.py
# Buat virtual environment
print_info "Membuat virtual environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
# Install Python dependencies
print_info "Menginstall Python dependencies..."
pip install --upgrade pip
pip install flask werkzeug
# Buat file service systemd
print_info "Membuat service systemd..."
cat > /etc/systemd/system/nftables-manager.service << EOF
[Unit]
Description=nftables Manager Web Interface
After=network.target
[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
# Reload systemd
systemctl daemon-reload
# Enable dan start service
print_info "Mengaktifkan dan menjalankan service..."
systemctl enable nftables-manager
systemctl start nftables-manager
# Tunggu service berjalan
sleep 3
# Cek status service
if systemctl is-active --quiet nftables-manager; then
    print_info "Service nftables-manager berhasil dijalankan"
else
    print_error "Service nftables-manager gagal dijalankan"
    systemctl status nftables-manager
    exit 1
fi
# Buat file konfigurasi nftables dasar jika belum ada
if [ ! -f /etc/nftables.conf ]; then
    print_info "Membuat file konfigurasi nftables dasar..."
    cat > /etc/nftables.conf << EOF
#!/usr/sbin/nft -f
# Basic nftables configuration
flush ruleset
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        
        # Allow loopback
        iifname lo accept
        
        # Allow established connections
        ct state established,related accept
        
        # Allow SSH (port 22)
        tcp dport 22 accept comment "Allow SSH"
        
        # Allow web management (port 2107)
        tcp dport 2107 accept comment "Allow Web Management"
        
        # Allow ICMP (ping)
        icmp type echo-request accept comment "Allow ICMP"
    }
    
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
EOF
    chmod 640 /etc/nftables.conf
fi
# Enable dan start nftables service
print_info "Mengaktifkan service nftables..."
systemctl enable nftables
systemctl restart nftables
# Cek status nftables
if systemctl is-active --quiet nftables; then
    print_info "Service nftables berhasil dijalankan"
else
    print_warning "Service nftables gagal dijalankan"
fi

# Buat symlink untuk akses mudah
ln -sf $APP_DIR /usr/local/bin/nftables-manager
print_info "Instalasi selesai!"
print_info "Akses aplikasi di: http://$(hostname -I | awk '{print $1}'):2107"
print_info "Login default: admin / admin123"
print_info "Untuk melihat log: journalctl -u nftables-manager -f"
print_info "Untuk menghentikan service: systemctl stop nftables-manager"