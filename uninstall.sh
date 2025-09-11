#!/bin/bash

# Script uninstallasi untuk nftables Manager
# Jalankan sebagai root: sudo ./uninstall.sh

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

print_info "Memulai uninstallasi nftables Manager..."

# Hentikan service nftables-manager
print_info "Menghentikan service nftables-manager..."
if systemctl is-active --quiet nftables-manager; then
    systemctl stop nftables-manager
    print_info "Service nftables-manager telah dihentikan"
else
    print_warning "Service nftables-manager tidak berjalan"
fi

# Nonaktifkan service nftables-manager
print_info "Menonaktifkan service nftables-manager..."
if systemctl is-enabled --quiet nftables-manager; then
    systemctl disable nftables-manager
    print_info "Service nftables-manager telah dinonaktifkan"
else
    print_warning "Service nftables-manager tidak diaktifkan"
fi

# Hapus file service systemd
print_info "Menghapus file service systemd..."
if [ -f /etc/systemd/system/nftables-manager.service ]; then
    rm -f /etc/systemd/system/nftables-manager.service
    print_info "File service telah dihapus"
else
    print_warning "File service tidak ditemukan"
fi

# Reload systemd
print_info "Me-reload systemd..."
systemctl daemon-reload

# Hapus direktori aplikasi
APP_DIR="/opt/nftables-manager"
if [ -d "$APP_DIR" ]; then
    print_info "Menghapus direktori aplikasi di $APP_DIR..."
    rm -rf "$APP_DIR"
    print_info "Direktori aplikasi telah dihapus"
else
    print_warning "Direktori aplikasi tidak ditemukan"
fi

# Hapus direktori database
DB_DIR="/var/lib/nftables_manager"
if [ -d "$DB_DIR" ]; then
    print_info "Menghapus direktori database di $DB_DIR..."
    rm -rf "$DB_DIR"
    print_info "Direktori database telah dihapus"
else
    print_warning "Direktori database tidak ditemukan"
fi

# Hapus direktori log
LOG_DIR="/var/log/nftables_manager"
if [ -d "$LOG_DIR" ]; then
    print_info "Menghapus direktori log di $LOG_DIR..."
    rm -rf "$LOG_DIR"
    print_info "Direktori log telah dihapus"
else
    print_warning "Direktori log tidak ditemukan"
fi

# Hapus direktori konfigurasi nftables
NFTABLES_DIR="/etc/nftables.d"
if [ -d "$NFTABLES_DIR" ]; then
    print_info "Menghapus direktori konfigurasi nftables di $NFTABLES_DIR..."
    rm -rf "$NFTABLES_DIR"
    print_info "Direktori konfigurasi nftables telah dihapus"
else
    print_warning "Direktori konfigurasi nftables tidak ditemukan"
fi

# Hapus symlink
if [ -L /usr/local/bin/nftables-manager ]; then
    print_info "Menghapus symlink..."
    rm -f /usr/local/bin/nftables-manager
    print_info "Symlink telah dihapus"
else
    print_warning "Symlink tidak ditemukan"
fi



# Tanyakan apakah ingin menghapus nftables
read -p "Apakah Anda ingin menghapus service nftables? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Menghapus service nftables..."
    if systemctl is-active --quiet nftables; then
        systemctl stop nftables
        print_info "Service nftables telah dihentikan"
    fi
    
    if systemctl is-enabled --quiet nftables; then
        systemctl disable nftables
        print_info "Service nftables telah dinonaktifkan"
    fi
    
    # Hapus paket nftables
    print_info "Menghapus paket nftables..."
    apt-get remove --purge -y nftables
    apt-get autoremove -y
    print_info "Paket nftables telah dihapus"
else
    print_info "Service nftables tidak dihapus"
fi

# Tanyakan apakah ingin menghapus dependensi Python
read -p "Apakah Anda ingin menghapus dependensi Python? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Menghapus dependensi Python..."
    apt-get remove --purge -y python3-pip python3-venv
    apt-get autoremove -y
    print_info "Dependensi Python telah dihapus"
else
    print_info "Dependensi Python tidak dihapus"
fi

# Tanyakan apakah ingin menghapus log dari journalctl
read -p "Apakah Anda ingin menghapus log dari journalctl? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Menghapus log dari journalctl..."
    journalctl --vacuum-time=1s -u nftables-manager
    print_info "Log journalctl telah dihapus"
else
    print_info "Log journalctl tidak dihapus"
fi

print_info "Uninstallasi selesai!"
print_info "Semua komponen nftables Manager telah dihapus dari sistem."