# nftables Manager

![nftables](https://img.shields.io/badge/nftables-firewall-blue.svg)
![Python](https://img.shields.io/badge/Python-3.x-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

Antarmuka web modern untuk mengelola firewall nftables dengan mudah dan aman.

## 📋 Table of Contents
- [Konfigurasi Awal](#konfigurasi-awal)
- [Panduan Penggunaan](#panduan-penggunaan)
  - [Manajemen Aturan Firewall](#1-manajemen-aturan-firewall)
  - [Manajemen Grup](#2-manajemen-grup)
  - [Backup & Restore](#3-backup--restore)
  - [Manajemen User](#4-manajemen-user)
  - [Monitoring & Debugging](#5-monitoring--debugging)
- [Contoh Konfigurasi](#contoh-konfigurasi)
- [Troubleshooting](#troubleshooting)
- [Keamanan](#keamanan)
- [API](#api)
- [Kontribusi](#kontribusi)
- [Lisensi](#lisensi)
- [Dukungan](#dukungan)
- [Changelog](#changelog)

---

## 🚀 Konfigurasi Awal

### Login Default
- **Username**: `admin`
- **Password**: `admin123`

> ⚠️ **PENTING**: Ubah password default segera setelah login pertama!

### Struktur IP dan Port
Aplikasi ini berjalan pada:
- **IP**: 0.0.0.0 (semua interface)
- **Port**: 5000

Untuk akses dari jaringan lain:
```bash
http://server-ip:5000



