# Nftables Manager

![nftables](https://img.shields.io/badge/nftables-firewall-blue.svg)
![Python](https://img.shields.io/badge/Python-3.x-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

Aplikasi web berbasis Flask untuk mengelola aturan firewall nftables 
dengan mudah. Aplikasi ini menyediakan antarmuka yang intuitif untuk 
mengelola aturan firewall, membuat grup aturan, dan melakukan backup 
konfigurasi.

## Fiktur
* Manajemen Aturan Firewall: Tambah, edit, hapus, dan aktifkan/nonaktifkan aturan nftables
* Pengelompokan Aturan: Kelompokkan aturan berdasarkan kategori (Management, Services, Security, Internal, Custom)
* Autentikasi Pengguna: Sistem login dengan password terenkripsi
* Backup & Restore: Backup konfigurasi nftables dan database, serta kemampuan restore dari backup
* Status Monitoring: Lihat status service nftables dan aturan yang sedang berjalan
 
## Persyaratan
* Python 3.6+
* Flask
* SQLite3
* nftables (terinstall di sistem)
* systemctl (untuk manajemen service)

## Instalasi
1. Clone repository
   ```bash
   git clone https://github.com/aqliserdadu/nftables-manager.git
   cd nftables-manager
   sudo chmod +x install.sh
   ```

### Login Default

- **Username**: `admin`
- **Password**: `admin123`

> ⚠️ **PENTING**: Ubah password default segera setelah login pertama!

### Struktur IP dan Port

Aplikasi ini berjalan pada:

- **IP**: 0.0.0.0 (semua interface)
- **Port**: 2107

Untuk akses dari jaringan lain:

```bash
http://server-ip:2107


```
