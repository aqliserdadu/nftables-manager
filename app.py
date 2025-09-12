from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import subprocess
import os
import shutil
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import logging
import secrets
import threading
import time

# Konfigurasi logging
logging.basicConfig(
    filename='/var/log/nftables_manager.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Konfigurasi Database
DB_FILE = "/var/lib/nftables_manager/firewall.db"
RULES_FILE = "/etc/nftables.d/custom.nft"
NFT_CONF = "/etc/nftables.conf"
BACKUP_DIR = "/etc/nftables.d/backups"

def adapt_datetime(ts):
    """Adapter untuk datetime ke SQLite"""
    return ts.isoformat()

def convert_datetime(ts):
    """Converter dari SQLite ke datetime"""
    try:
        return datetime.fromisoformat(ts.decode())
    except:
        try:
            # Coba format dengan 'T' (ISO 8601)
            return datetime.strptime(ts.decode(), "%Y-%m-%dT%H:%M:%S")
        except:
            # Coba format dengan spasi
            return datetime.strptime(ts.decode(), "%Y-%m-%d %H:%M:%S")

# Register adapters dan converters
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)
sqlite3.register_converter("TIMESTAMP", convert_datetime)

# Fungsi untuk menonaktifkan aturan yang sudah expired
def check_expired_rules():
    """Memeriksa dan menonaktifkan aturan yang sudah melewati waktu expired"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Dapatkan waktu saat ini
        current_time = datetime.now()
        
        # Cari aturan yang sudah expired tapi masih aktif
        c.execute("""
            SELECT id, name FROM rules 
            WHERE expired_at IS NOT NULL 
            AND datetime(expired_at) <= datetime(?) 
            AND enabled = 1
        """, (current_time.isoformat(),))
        
        expired_rules = c.fetchall()
        
        if expired_rules:
            logging.info(f"Found {len(expired_rules)} expired rules to disable")
            
            # Nonaktifkan aturan yang sudah expired
            for rule in expired_rules:
                c.execute("""
                    UPDATE rules SET enabled = 0, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (rule[0],))
                logging.info(f"Disabled expired rule: {rule[1]} (ID: {rule[0]})")
            
            conn.commit()
            
            # Simpan perubahan ke file konfigurasi
            save_rules()
            
        conn.close()
        
    except Exception as e:
        logging.error(f"Error checking expired rules: {e}")

# Fungsi untuk menjalankan pengecekan aturan expired secara berkala
def expired_rules_checker():
    """Menjalankan pengecekan aturan expired setiap jam"""
    while True:
        try:
            check_expired_rules()
            time.sleep(3600)  # 1 jam sebelum pengecekan lanjut kembali
        except Exception as e:
            logging.error(f"Error in expired rules checker: {e}")
            time.sleep(300)

# Fungsi untuk membuat direktori jika belum ada
def ensure_directory_exists(path):
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, mode=0o750)
            logging.info(f"Created directory: {directory}")
            return True
        except Exception as e:
            logging.error(f"Error creating directory {directory}: {e}")
            return False
    return True

# Fungsi backup konfigurasi dan database
def backup_config():
    """Backup konfigurasi nftables dan database"""
    try:
        logging.info("=== Starting backup process ===")
        
        if not ensure_directory_exists(BACKUP_DIR):
            logging.error(f"Failed to create backup directory: {BACKUP_DIR}")
            return False, "Failed to create backup directory"
        
        logging.info(f"Backup directory exists: {BACKUP_DIR}")
        
        if not os.access(BACKUP_DIR, os.W_OK):
            logging.error(f"No write permission for backup directory: {BACKUP_DIR}")
            return False, f"No write permission for backup directory"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_subdir = os.path.join(BACKUP_DIR, f"backup_{timestamp}")
        
        try:
            os.makedirs(backup_subdir, mode=0o750)
            logging.info(f"Created backup subdirectory: {backup_subdir}")
        except Exception as e:
            logging.error(f"Error creating backup subdirectory: {e}")
            return False, f"Error creating backup subdirectory: {e}"
        
        # Backup file konfigurasi nftables
        if os.path.exists(NFT_CONF):
            nft_backup_file = os.path.join(backup_subdir, "nftables.conf")
            try:
                shutil.copy2(NFT_CONF, nft_backup_file)
                os.chmod(nft_backup_file, 0o640)
                logging.info(f"Backed up nftables config to {nft_backup_file}")
            except Exception as e:
                logging.error(f"Error backing up nftables config: {e}")
                return False, f"Error backing up nftables config: {e}"
        else:
            logging.warning(f"nftables config file {NFT_CONF} does not exist")
            nft_backup_file = os.path.join(backup_subdir, "nftables.conf")
            try:
                with open(nft_backup_file, 'w') as f:
                    f.write("# Empty nftables config\n")
                os.chmod(nft_backup_file, 0o640)
                logging.info(f"Created empty nftables config file: {nft_backup_file}")
            except Exception as e:
                logging.error(f"Error creating empty nftables config: {e}")
        
        # Backup database
        if os.path.exists(DB_FILE):
            db_backup_file = os.path.join(backup_subdir, "firewall.db")
            try:
                shutil.copy2(DB_FILE, db_backup_file)
                os.chmod(db_backup_file, 0o640)
                logging.info(f"Backed up database to {db_backup_file}")
            except Exception as e:
                logging.error(f"Error backing up database: {e}")
                return False, f"Error backing up database: {e}"
        else:
            logging.warning(f"Database file {DB_FILE} does not exist")
            db_backup_file = os.path.join(backup_subdir, "firewall.db")
            try:
                conn = sqlite3.connect(db_backup_file)
                conn.close()
                os.chmod(db_backup_file, 0o640)
                logging.info(f"Created empty database file: {db_backup_file}")
            except Exception as e:
                logging.error(f"Error creating empty database: {e}")
        
        # Buat file info backup
        info_file = os.path.join(backup_subdir, "backup_info.txt")
        try:
            with open(info_file, 'w') as f:
                f.write(f"Backup created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"nftables config: {NFT_CONF}\n")
                f.write(f"Database: {DB_FILE}\n")
                f.write(f"User: {session.get('username', 'Unknown')}\n")
            os.chmod(info_file, 0o640)
            logging.info(f"Created backup info file: {info_file}")
        except Exception as e:
            logging.error(f"Error creating backup info file: {e}")
        
        # Verifikasi backup files exist
        nft_exists = os.path.exists(os.path.join(backup_subdir, "nftables.conf"))
        db_exists = os.path.exists(os.path.join(backup_subdir, "firewall.db"))
        info_exists = os.path.exists(os.path.join(backup_subdir, "backup_info.txt"))
        
        logging.info(f"Backup verification - nftables: {nft_exists}, db: {db_exists}, info: {info_exists}")
        
        if nft_exists and db_exists and info_exists:
            return True, f"Backup created: {backup_subdir}"
        else:
            return False, f"Backup incomplete - nftables: {nft_exists}, db: {db_exists}, info: {info_exists}"
        
    except Exception as e:
        logging.error(f"Unexpected error in backup_config: {e}")
        return False, f"Unexpected error: {e}"

# Fungsi untuk mendapatkan daftar backup
def get_backup_list():
    """Mendapatkan daftar backup yang tersedia"""
    backups = []
    try:
        logging.info(f"Checking for backups in: {BACKUP_DIR}")
        
        if os.path.exists(BACKUP_DIR):
            logging.info("Backup directory exists")
            
            for item in os.listdir(BACKUP_DIR):
                item_path = os.path.join(BACKUP_DIR, item)
                if os.path.isdir(item_path) and item.startswith("backup_"):
                    try:
                        info_file = os.path.join(item_path, "backup_info.txt")
                        backup_time = datetime.fromtimestamp(os.path.getctime(item_path))
                        
                        has_nftables = os.path.exists(os.path.join(item_path, "nftables.conf"))
                        has_db = os.path.exists(os.path.join(item_path, "firewall.db"))
                        has_info = os.path.exists(os.path.join(item_path, "backup_info.txt"))
                        
                        total_size = 0
                        for root, dirs, files in os.walk(item_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                try:
                                    total_size += os.path.getsize(file_path)
                                except:
                                    pass
                        
                        backups.append({
                            'name': item,
                            'path': item_path,
                            'created': backup_time,
                            'has_nftables': has_nftables,
                            'has_db': has_db,
                            'has_info': has_info,
                            'size': total_size
                        })
                        logging.info(f"Found backup: {item} (nftables: {has_nftables}, db: {has_db}, info: {has_info})")
                    except Exception as e:
                        logging.error(f"Error processing backup {item}: {e}")
            
            backups.sort(key=lambda x: x['created'], reverse=True)
            logging.info(f"Total backups found: {len(backups)}")
        else:
            logging.warning("Backup directory does not exist")
            
    except Exception as e:
        logging.error(f"Error getting backup list: {e}")
    
    return backups

# Fungsi untuk menghapus backup
def delete_backup(backup_path):
    """Hapus direktori backup"""
    try:
        logging.info(f"=== Starting delete backup: {backup_path} ===")
        
        if not os.path.exists(backup_path):
            logging.error(f"Backup directory not found: {backup_path}")
            return False, "Backup directory not found"
        
        if not os.path.basename(backup_path).startswith("backup_"):
            logging.error(f"Invalid backup directory: {backup_path}")
            return False, "Invalid backup directory"
        
        try:
            shutil.rmtree(backup_path)
            logging.info(f"Successfully deleted backup: {backup_path}")
            return True, f"Backup deleted: {os.path.basename(backup_path)}"
        except Exception as e:
            logging.error(f"Error deleting backup: {e}")
            return False, f"Error deleting backup: {e}"
            
    except Exception as e:
        logging.error(f"Unexpected error in delete_backup: {e}")
        return False, f"Unexpected error: {e}"

# Fungsi restore dari backup
def restore_from_backup(backup_path):
    """Restore konfigurasi dan database dari backup"""
    try:
        logging.info(f"=== Starting restore from: {backup_path} ===")
        
        backup_success, backup_message = backup_config()
        if not backup_success:
            logging.warning(f"Backup before restore failed: {backup_message}")
        
        if not os.path.exists(backup_path):
            logging.error(f"Backup directory not found: {backup_path}")
            return False, "Backup directory not found"
        
        # Restore database
        db_backup_file = os.path.join(backup_path, "firewall.db")
        if os.path.exists(db_backup_file):
            try:
                if os.path.exists(DB_FILE):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    pre_restore_db_backup = f"{DB_FILE}.prerestore_{timestamp}"
                    shutil.copy2(DB_FILE, pre_restore_db_backup)
                    os.chmod(pre_restore_db_backup, 0o640)
                    logging.info(f"Pre-restore database backup: {pre_restore_db_backup}")
                
                shutil.copy2(db_backup_file, DB_FILE)
                os.chmod(DB_FILE, 0o640)
                logging.info(f"Restored database from {db_backup_file}")
                
            except Exception as e:
                logging.error(f"Error restoring database: {e}")
                return False, f"Error restoring database: {e}"
        else:
            logging.warning("Database file not found in backup")
        
        # Restore file konfigurasi nftables
        nft_backup_file = os.path.join(backup_path, "nftables.conf")
        if os.path.exists(nft_backup_file):
            try:
                shutil.copy2(nft_backup_file, NFT_CONF)
                os.chmod(NFT_CONF, 0o640)
                logging.info(f"Restored nftables config from {nft_backup_file}")
                
            except Exception as e:
                logging.error(f"Error restoring nftables config: {e}")
                return False, f"Error restoring nftables config: {e}"
        else:
            logging.warning("nftables config file not found in backup")
        
        # Reload nftables
        success, message = reload_nft()
        if success:
            logging.info(f"Successfully restored configuration from {backup_path}")
            return True, f"Configuration restored from {backup_path}"
        else:
            logging.error(f"Failed to reload nftables after restore: {message}")
            return False, f"Restored files but failed to reload nftables: {message}"
            
    except Exception as e:
        logging.error(f"Error restoring from backup: {e}")
        return False, f"Error restoring from backup: {e}"

# Fungsi untuk mengecek status nftables
def check_nftables_status():
    """Mengecek status service nftables"""
    try:
        check_service = subprocess.run(['/usr/bin/systemctl', 'is-enabled', 'nftables'], 
                                     capture_output=True, text=True)
        
        if check_service.returncode != 0:
            return {
                'installed': False,
                'enabled': False,
                'active': False,
                'message': 'nftables service is not installed'
            }
        
        status_result = subprocess.run(['/usr/bin/systemctl', 'is-active', 'nftables'], 
                                    capture_output=True, text=True)
        
        is_active = status_result.returncode == 0
        
        enabled_result = subprocess.run(['/usr/bin/systemctl', 'is-enabled', 'nftables'], 
                                      capture_output=True, text=True)
        
        is_enabled = enabled_result.returncode == 0
        
        status_detail = subprocess.run(['/usr/bin/systemctl', 'status', 'nftables'], 
                                    capture_output=True, text=True)
        
        return {
            'installed': True,
            'enabled': is_enabled,
            'active': is_active,
            'message': status_detail.stdout if status_detail.returncode == 0 else status_detail.stderr
        }
    except Exception as e:
        logging.error(f"Error checking nftables status: {e}")
        return {
            'installed': False,
            'enabled': False,
            'active': False,
            'message': str(e)
        }

# Fungsi untuk mengubah password user
def change_password(user_id, current_password, new_password):
    """Mengubah password user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("SELECT password FROM users WHERE id=?", (user_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return False, "User not found"
    
    current_hash = result[0]
    
    if not check_password_hash(current_hash, current_password):
        conn.close()
        return False, "Current password is incorrect"
    
    new_hash = generate_password_hash(new_password)
    
    try:
        c.execute("UPDATE users SET password=? WHERE id=?", (new_hash, user_id))
        conn.commit()
        conn.close()
        logging.info(f"Password changed for user ID: {user_id}")
        return True, "Password changed successfully"
    except Exception as e:
        conn.close()
        logging.error(f"Error changing password: {e}")
        return False, f"Error changing password: {e}"

# Inisialisasi Database
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabel untuk user login
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    
    # Tabel untuk grup aturan
    c.execute("""
        CREATE TABLE IF NOT EXISTS rule_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            color TEXT DEFAULT '#6c757d',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabel untuk aturan firewall
    c.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            group_id INTEGER,
            chain TEXT NOT NULL,
            src TEXT,
            dst TEXT,
            dport TEXT,
            protocol TEXT,
            action TEXT NOT NULL,
            comment TEXT,
            enabled BOOLEAN DEFAULT 1,
            expired_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES rule_groups(id)
        )
    """)
    
    # Cek apakah kolom expired_at sudah ada
    c.execute("PRAGMA table_info(rules)")
    columns = [column[1] for column in c.fetchall()]
    
    if 'expired_at' not in columns:
        logging.info("Adding expired_at column to rules table")
        c.execute("ALTER TABLE rules ADD COLUMN expired_at TIMESTAMP")
        conn.commit()
    
    # Buat user default jika belum ada
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                 ('admin', generate_password_hash('admin123')))
    
    # Buat grup default jika belum ada
    default_groups = [
        ('Management', 'Akses untuk manajemen jaringan', '#0d6efd'),
        ('Services', 'Aturan untuk layanan publik', '#198754'),
        ('Security', 'Aturan keamanan dan pemblokiran', '#dc3545'),
        ('Internal', 'Akses jaringan internal', '#6f42c1'),
        ('Custom', 'Aturan kustom', '#fd7e14')
    ]
    
    for name, desc, color in default_groups:
        c.execute("SELECT * FROM rule_groups WHERE name=?", (name,))
        if not c.fetchone():
            c.execute("INSERT INTO rule_groups (name, description, color) VALUES (?, ?, ?)",
                     (name, desc, color))
    
    # Tambahkan aturan default untuk port 22 (SSH)
    c.execute("""
        SELECT COUNT(*) FROM rules 
        WHERE name = 'Allow SSH' AND dport = '22'
    """)
    ssh_rule_count = c.fetchone()[0]
    
    if ssh_rule_count == 0:
        c.execute("SELECT id FROM rule_groups WHERE name = 'Management'")
        management_group = c.fetchone()
        group_id = management_group[0] if management_group else None
        
        c.execute("""
            INSERT INTO rules (name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'Allow SSH', group_id, 'input', None, None, '22', 'tcp', 'accept', 
            'Allow SSH access for remote administration', True, None
        ))
        logging.info("Added default rule for port 22 (SSH)")
    
    # Tambahkan aturan default untuk port 2107
    c.execute("""
        SELECT COUNT(*) FROM rules 
        WHERE name = 'Allow Web Management' AND dport = '2107'
    """)
    rule_count = c.fetchone()[0]
    
    if rule_count == 0:
        c.execute("SELECT id FROM rule_groups WHERE name = 'Services'")
        services_group = c.fetchone()
        group_id = services_group[0] if services_group else None
        
        c.execute("""
            INSERT INTO rules (name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'Allow Web Management', group_id, 'input', None, None, '2107', 'tcp', 'accept', 
            'Allow access to web management interface', True, None
        ))
        logging.info("Added default rule for port 2107 (Web Management)")
    
    # Tambahkan aturan default untuk ICMP (ping)
    c.execute("""
        SELECT COUNT(*) FROM rules 
        WHERE name = 'Allow ICMP (Ping)' AND protocol = 'icmp'
    """)
    icmp_rule_count = c.fetchone()[0]
    
    if icmp_rule_count == 0:
        c.execute("SELECT id FROM rule_groups WHERE name = 'Management'")
        management_group = c.fetchone()
        group_id = management_group[0] if management_group else None
        
        c.execute("""
            INSERT INTO rules (name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'Allow ICMP (Ping)', group_id, 'input', None, None, None, 'icmp', 'accept', 
            'Allow ICMP echo requests for monitoring and troubleshooting', True, None
        ))
        logging.info("Added default rule for ICMP (Ping)")
    
    conn.commit()
    conn.close()
    
    # Pastikan direktori untuk file konfigurasi ada
    logging.info("=== Initializing directories ===")
    ensure_directory_exists(RULES_FILE)
    ensure_directory_exists(BACKUP_DIR)
    
    logging.info(f"Rules file path: {RULES_FILE}")
    logging.info(f"NFT config path: {NFT_CONF}")
    logging.info(f"Backup directory: {BACKUP_DIR}")
    
    if os.path.exists(BACKUP_DIR):
        logging.info("Backup directory exists")
        try:
            files = os.listdir(BACKUP_DIR)
            logging.info(f"Files in backup directory: {files}")
        except Exception as e:
            logging.error(f"Error listing backup directory: {e}")
    else:
        logging.warning("Backup directory does not exist")
    
    if not os.path.exists(NFT_CONF):
        logging.warning(f"nftables config file {NFT_CONF} does not exist, creating empty file")
        try:
            with open(NFT_CONF, 'w') as f:
                f.write("# Empty nftables config\n")
            os.chmod(NFT_CONF, 0o640)
            logging.info(f"Created empty nftables config file: {NFT_CONF}")
        except Exception as e:
            logging.error(f"Error creating empty nftables config: {e}")

# Fungsi Database
def get_groups():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM rule_groups ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return rows

def get_group(group_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM rule_groups WHERE id=?", (group_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_rules(group_id=None):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    current_time = datetime.now()
    
    if group_id:
        c.execute("""
            SELECT r.*, g.name as group_name, g.color as group_color 
            FROM rules r 
            LEFT JOIN rule_groups g ON r.group_id = g.id 
            WHERE r.group_id = ? 
            ORDER BY r.name
        """, (group_id,))
    else:
        c.execute("""
            SELECT r.*, g.name as group_name, g.color as group_color 
            FROM rules r 
            LEFT JOIN rule_groups g ON r.group_id = g.id 
            ORDER BY g.name, r.name
        """)
    
    rows = c.fetchall()
    conn.close()
    
    rules = [dict(row) for row in rows]
    
    updated_rules = []
    for rule in rules:
        if rule['expired_at'] and rule['enabled']:
            try:
                try:
                    expired_at = datetime.fromisoformat(rule['expired_at'])
                except ValueError:
                    expired_at = datetime.strptime(rule['expired_at'], '%Y-%m-%d %H:%M:%S')
                
                if expired_at <= current_time:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""
                        UPDATE rules SET enabled = 0, updated_at = CURRENT_TIMESTAMP 
                        WHERE id = ?
                    """, (rule['id'],))
                    conn.commit()
                    conn.close()
                    
                    rule['enabled'] = 0
                    logging.info(f"Disabled expired rule: {rule['name']} (ID: {rule['id']})")
            except (ValueError, TypeError) as e:
                logging.error(f"Error parsing expired_at for rule {rule['name']}: {e}")
        
        updated_rules.append(rule)
    
    return updated_rules

def get_rule(rule_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT r.*, g.name as group_name, g.color as group_color 
        FROM rules r 
        LEFT JOIN rule_groups g ON r.group_id = g.id 
        WHERE r.id = ?
    """, (rule_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def add_rule_to_db(name, group_id, chain, src, dst, dport, protocol, action, comment, enabled=True, expired_at=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO rules (name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at))
    conn.commit()
    rule_id = c.lastrowid
    conn.close()
    return rule_id

def update_rule_in_db(rule_id, name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        UPDATE rules SET name=?, group_id=?, chain=?, src=?, dst=?, dport=?, protocol=?, 
        action=?, comment=?, enabled=?, expired_at=?, updated_at=CURRENT_TIMESTAMP 
        WHERE id=?
    """, (name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at, rule_id))
    conn.commit()
    conn.close()

def delete_rule_from_db(rule_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    conn.commit()
    conn.close()

def toggle_rule_in_db(rule_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE rules SET enabled = NOT enabled, updated_at=CURRENT_TIMESTAMP WHERE id=?", (rule_id,))
    conn.commit()
    conn.close()

# Fungsi nftablesdef save_rules():
def save_rules():
    """Simpan aturan ke file dan reload nftables"""
    try:
        logging.info("=== Starting save_rules process ===")
        if not ensure_directory_exists(RULES_FILE):
            logging.error("Failed to create configuration directory")
            return False, "Failed to create configuration directory"
        rules = get_rules()
        logging.info(f"Found {len(rules)} rules in database")
        
        # Pertama cek apakah tabel sudah ada
        try:
            result = subprocess.run(['/usr/sbin/nft', 'list', 'tables'], 
                                  capture_output=True, text=True)
            table_exists = 'inet tableku' in result.stdout
            logging.info(f"Table 'tableku' exists: {table_exists}")
        except Exception as e:
            logging.error(f"Error checking table existence: {e}")
            table_exists = False
        
        config = """#!/usr/sbin/nft -f
"""
        
        # Hanya hapus tabel jika sudah ada
        if table_exists:
            config += """# Hapus tabel yang sudah ada
flush ruleset
"""
        
        config += """# Tabel baru
table inet tableku {
    chain input {
        type filter hook input priority 0; policy drop;
        # Allow loopback
        iifname lo accept
        # Allow established connections
        ct state established,related accept
"""
        # buffer aturan tiap chain
        chain_rules = {
            "input": "",
            "forward": "",
            "output": "",
        }
        enabled_rules = 0
        for rule in rules:
            if not rule['enabled']:
                continue
            enabled_rules += 1
            rule_str = "        "
            # Tambahkan komentar nama rule
            if rule['name']:
                group_name = rule['group_name'] if rule['group_name'] else "Ungrouped"
                rule_str += f"# {rule['name']} [{group_name}]\n        "
            # Sumber / tujuan
            if rule['src']:
                rule_str += f"ip saddr {rule['src']} "
            if rule['dst']:
                rule_str += f"ip daddr {rule['dst']} "
            # Protokol & port
            if rule['protocol'] and rule['protocol'].lower() == 'icmp':
                rule_str += "icmp type echo-request accept"
            elif rule['dport']:
                protocol = rule['protocol'] if rule['protocol'] else 'tcp'
                rule_str += f"{protocol} dport {rule['dport']} "
            elif rule['protocol']:
                rule_str += f"{rule['protocol']} "
            # Aksi (kecuali ICMP echo-request sudah fixed)
            if not (rule['protocol'] and rule['protocol'].lower() == 'icmp'):
                rule_str += rule['action']
            # Komentar tambahan
            if rule['comment']:
                rule_str += f" # {rule['comment']}"
            rule_str += "\n"
            # Masukkan rule ke chain sesuai rule['chain']
            chain_name = rule['chain'].lower()
            if chain_name in chain_rules:
                chain_rules[chain_name] += rule_str
            else:
                logging.warning(f"Unknown chain: {rule['chain']}")
        # susun ulang config
        config += chain_rules["input"]
        config += """    }
    chain forward {
        type filter hook forward priority 0; policy drop;
"""
        config += chain_rules["forward"]
        config += """    }
    chain output {
        type filter hook output priority 0; policy accept;
"""
        config += chain_rules["output"]
        config += """    }
}
"""
        logging.info(f"Generated config with {enabled_rules} enabled rules")
        # Simpan ke file & reload nft
        try:
            with open(RULES_FILE, "w") as f:
                f.write(config)
            os.chmod(RULES_FILE, 0o640)
            logging.info(f"Rules saved to {RULES_FILE}")
            success, message = reload_nft()
            if not success:
                return False, message
            return True, "Rules saved successfully"
        except Exception as e:
            logging.error(f"Error saving rules: {e}")
    except Exception as e:
        logging.error(f"Unexpected error in save_rules: {e}")
        return False, f"Unexpected error: {e}"

        
def reload_nft():
    """Reload konfigurasi nftables"""
    try:
        logging.info("=== Starting reload_nft process ===")
        
        logging.info(f"Copying {RULES_FILE} to {NFT_CONF}")
        try:
            subprocess.run(["/usr/bin/cp", RULES_FILE, NFT_CONF], check=True)
            logging.info("File copy successful")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error copying file: {e}")
            return False, f"Error copying file: {e}"
        
        logging.info("Restarting nftables service...")
        try:
            result = subprocess.run(["/usr/bin/systemctl", "restart", "nftables"], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logging.error(f"Error restarting nftables: {result.stderr}")
                return False, f"Error restarting nftables: {result.stderr}"
            logging.info("nftables reloaded successfully")
            return True, "nftables reloaded successfully"
        except subprocess.CalledProcessError as e:
            logging.error(f"Error in systemctl command: {e}")
            return False, f"Error in systemctl command: {e}"
            
    except Exception as e:
        logging.error(f"Unexpected error in reload_nft: {e}")
        return False, f"Unexpected error: {e}"

# Autentikasi
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session.permanent = True
            flash('Login successful!', 'success')
            logging.info(f"User {username} logged in")
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
            logging.warning(f"Failed login attempt for username: {username}")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username', 'Unknown')
    session.clear()
    flash('You have been logged out', 'info')
    logging.info(f"User {username} logged out")
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password_route():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('New password and confirmation do not match!', 'danger')
            return render_template('change_password.html')
        
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long!', 'danger')
            return render_template('change_password.html')
        
        success, message = change_password(session['user_id'], current_password, new_password)
        
        if success:
            flash(message, 'success')
            return redirect(url_for('dashboard'))
        else:
            flash(message, 'danger')
    
    return render_template('change_password.html')

@app.route('/dashboard')
@login_required
def dashboard():
    group_id = request.args.get('group_id', type=int)
    rules = get_rules(group_id)
    groups = get_groups()
    selected_group = get_group(group_id) if group_id else None
    
    return render_template('dashboard.html', 
                          rules=rules, 
                          groups=groups, 
                          selected_group=selected_group,
                          datetime=datetime)

@app.route('/add_rule', methods=['GET', 'POST'])
@login_required
def add_rule_route():
    groups = get_groups()
    
    if request.method == 'POST':
        name = request.form['name']
        group_id = request.form['group_id'] or None
        chain = request.form['chain']
        src = request.form['src']
        dst = request.form['dst']
        dport = request.form['dport']
        protocol = request.form['protocol']
        action = request.form['action']
        comment = request.form['comment']
        enabled = 'enabled' in request.form
        
        expired_at = None
        has_expiry = 'has_expiry' in request.form
        if has_expiry:
            if 'expired_date' in request.form and request.form['expired_date']:
                expired_date = request.form['expired_date']
                expired_time = request.form.get('expired_time', '00:00')
                expired_at_str = f"{expired_date} {expired_time}"
                try:
                    expired_at = datetime.strptime(expired_at_str, '%Y-%m-%d %H:%M')
                except ValueError:
                    flash('Invalid expiration date/time format!', 'danger')
                    return render_template('add_rule.html', groups=groups, 
                                          form_data=request.form, datetime=datetime)
        
        if dport and not protocol:
            flash('Protocol is required when specifying a port!', 'danger')
            return render_template('add_rule.html', groups=groups, 
                                  form_data=request.form, datetime=datetime)
        
        try:
            rule_id = add_rule_to_db(name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at)
            logging.info(f"Added rule {name} (ID: {rule_id}) to database")
            
            success, message = save_rules()
            
            if success:
                flash('Rule added successfully!', 'success')
            else:
                flash(f'Rule added to database but failed to apply: {message}', 'warning')
            
            return redirect(url_for('dashboard'))
        except Exception as e:
            logging.error(f"Error adding rule: {e}")
            flash(f'Error adding rule: {e}', 'danger')
    
    return render_template('add_rule.html', groups=groups, datetime=datetime)

@app.route('/edit/<int:rule_id>', methods=['GET', 'POST'])
@login_required
def edit_rule(rule_id):
    rule = get_rule(rule_id)
    if not rule:
        flash('Rule not found', 'danger')
        return redirect(url_for('dashboard'))
    
    rule_dict = dict(rule)
    groups = get_groups()
    
    if request.method == 'POST':
        name = request.form['name']
        group_id = request.form['group_id'] or None
        chain = request.form['chain']
        src = request.form['src']
        dst = request.form['dst']
        dport = request.form['dport']
        protocol = request.form['protocol']
        action = request.form['action']
        comment = request.form['comment']
        enabled = 'enabled' in request.form
        
        expired_at = None
        has_expiry = 'has_expiry' in request.form
        if has_expiry:
            if 'expired_date' in request.form and request.form['expired_date']:
                expired_date = request.form['expired_date']
                expired_time = request.form.get('expired_time', '00:00')
                expired_at_str = f"{expired_date} {expired_time}"
                try:
                    expired_at = datetime.strptime(expired_at_str, '%Y-%m-%d %H:%M')
                except ValueError:
                    flash('Invalid expiration date/time format!', 'danger')
                    return render_template('edit_rule.html', rule=rule_dict, groups=groups, 
                                          form_data=request.form, datetime=datetime)
        
        if dport and not protocol:
            flash('Protocol is required when specifying a port!', 'danger')
            return render_template('edit_rule.html', rule=rule_dict, groups=groups, 
                                  form_data=request.form, datetime=datetime)
        
        try:
            update_rule_in_db(rule_id, name, group_id, chain, src, dst, dport, protocol, action, comment, enabled, expired_at)
            logging.info(f"Updated rule {name} (ID: {rule_id}) in database")
            
            success, message = save_rules()
            
            if success:
                flash('Rule updated successfully!', 'success')
            else:
                flash(f'Rule updated in database but failed to apply: {message}', 'warning')
            
            return redirect(url_for('dashboard'))
        except Exception as e:
            logging.error(f"Error updating rule: {e}")
            flash(f'Error updating rule: {e}', 'danger')
    
    if rule_dict['expired_at']:
        try:
            try:
                expired_datetime = datetime.fromisoformat(rule_dict['expired_at'])
            except ValueError:
                expired_datetime = datetime.strptime(rule_dict['expired_at'], '%Y-%m-%d %H:%M:%S')
            
            rule_dict['expired_date'] = expired_datetime.strftime('%Y-%m-%d')
            rule_dict['expired_time'] = expired_datetime.strftime('%H:%M')
        except (ValueError, TypeError) as e:
            logging.error(f"Error parsing expired_at for rule {rule_dict['name']}: {e}")
            rule_dict['expired_date'] = ''
            rule_dict['expired_time'] = '00:00'
    else:
        rule_dict['expired_date'] = ''
        rule_dict['expired_time'] = '00:00'
    
    return render_template('edit_rule.html', rule=rule_dict, groups=groups, datetime=datetime)

@app.route('/delete/<int:rule_id>')
@login_required
def delete_rule_route(rule_id):
    try:
        delete_rule_from_db(rule_id)
        logging.info(f"Deleted rule ID: {rule_id} from database")
        
        success, message = save_rules()
        
        if success:
            flash('Rule deleted successfully!', 'success')
        else:
            flash(f'Rule deleted from database but failed to apply changes: {message}', 'warning')
    except Exception as e:
        logging.error(f"Error deleting rule: {e}")
        flash(f'Error deleting rule: {e}', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/toggle/<int:rule_id>')
@login_required
def toggle_rule_route(rule_id):
    try:
        toggle_rule_in_db(rule_id)
        logging.info(f"Toggled rule ID: {rule_id} in database")
        
        success, message = save_rules()
        
        if success:
            flash('Rule status updated successfully!', 'success')
        else:
            flash(f'Rule status updated in database but failed to apply: {message}', 'warning')
    except Exception as e:
        logging.error(f"Error toggling rule: {e}")
        flash(f'Error toggling rule: {e}', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/groups')
@login_required
def manage_groups():
    groups = get_groups()
    return render_template('groups.html', groups=groups)

@app.route('/add_group', methods=['GET', 'POST'])
@login_required
def add_group():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        color = request.form['color']
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO rule_groups (name, description, color) VALUES (?, ?, ?)",
                     (name, description, color))
            conn.commit()
            flash('Group added successfully!', 'success')
            logging.info(f"Added group: {name}")
            return redirect(url_for('manage_groups'))
        except sqlite3.IntegrityError:
            flash('Group name already exists!', 'danger')
        finally:
            conn.close()
    
    return render_template('add_group.html')

@app.route('/edit_group/<int:group_id>', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    group = get_group(group_id)
    if not group:
        flash('Group not found', 'danger')
        return redirect(url_for('manage_groups'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        color = request.form['color']
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        try:
            c.execute("""
                UPDATE rule_groups SET name=?, description=?, color=? 
                WHERE id=?
            """, (name, description, color, group_id))
            conn.commit()
            flash('Group updated successfully!', 'success')
            logging.info(f"Updated group: {name}")
            return redirect(url_for('manage_groups'))
        except sqlite3.IntegrityError:
            flash('Group name already exists!', 'danger')
        finally:
            conn.close()
    
    return render_template('edit_group.html', group=group)

@app.route('/delete_group/<int:group_id>')
@login_required
def delete_group(group_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM rules WHERE group_id=?", (group_id,))
    count = c.fetchone()[0]
    conn.close()
    
    if count > 0:
        flash('Cannot delete group with associated rules!', 'danger')
    else:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM rule_groups WHERE id=?", (group_id,))
        conn.commit()
        conn.close()
        flash('Group deleted successfully!', 'success')
        logging.info(f"Deleted group ID: {group_id}")
    
    return redirect(url_for('manage_groups'))

@app.route('/status')
@login_required
def status():
    try:
        result = subprocess.run(['/usr/sbin/nft', 'list', 'ruleset'], 
                                capture_output=True, text=True, check=True)
        return render_template('status.html', ruleset=result.stdout)
    except subprocess.CalledProcessError as e:
        flash(f'Error getting nftables status: {e}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/config')
@login_required
def config():
    return render_template('config.html', 
                          rules_file=RULES_FILE, 
                          nft_conf=NFT_CONF,
                          backup_dir=BACKUP_DIR)

@app.route('/backups')
@login_required
def backups():
    backup_list = get_backup_list()
    return render_template('backups.html', backups=backup_list, backup_dir=BACKUP_DIR)

@app.route('/restore/<path:backup_name>')
@login_required
def restore_backup(backup_name):
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    if not os.path.exists(backup_path):
        flash('Backup directory not found!', 'danger')
        return redirect(url_for('backups'))
    
    success, message = restore_from_backup(backup_path)
    if success:
        flash(message, 'success')
        flash('Database restored. Please restart the application to see changes.', 'info')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('backups'))

@app.route('/delete_backup/<path:backup_name>')
@login_required
def delete_backup_route(backup_name):
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    if not os.path.exists(backup_path):
        flash('Backup directory not found!', 'danger')
        return redirect(url_for('backups'))
    
    success, message = delete_backup(backup_path)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('backups'))

@app.route('/apply_rules', methods=['POST'])
@login_required
def apply_rules():
    success, message = save_rules()
    if success:
        flash('Rules applied successfully!', 'success')
    else:
        flash(f'Failed to apply rules: {message}', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/debug/backup')
@login_required
def debug_backup():
    debug_info = {
        'backup_dir_exists': os.path.exists(BACKUP_DIR),
        'backup_dir_path': BACKUP_DIR,
        'nft_conf_exists': os.path.exists(NFT_CONF),
        'nft_conf_path': NFT_CONF,
        'db_exists': os.path.exists(DB_FILE),
        'db_path': DB_FILE,
        'backup_dirs': [],
        'current_user': os.getenv('USER', 'unknown'),
        'backup_dir_permissions': None,
        'nft_conf_permissions': None,
        'db_permissions': None,
        'test_backup_success': None,
        'test_backup_message': None
    }
    
    if os.path.exists(BACKUP_DIR):
        try:
            debug_info['backup_dir_permissions'] = oct(os.stat(BACKUP_DIR).st_mode)[-3:]
        except:
            pass
    
    if os.path.exists(NFT_CONF):
        try:
            debug_info['nft_conf_permissions'] = oct(os.stat(NFT_CONF).st_mode)[-3:]
        except:
            pass
    
    if os.path.exists(DB_FILE):
        try:
            debug_info['db_permissions'] = oct(os.stat(DB_FILE).st_mode)[-3:]
        except:
            pass
    
    if os.path.exists(BACKUP_DIR):
        try:
            items = os.listdir(BACKUP_DIR)
            debug_info['backup_dir_contents'] = items
            for item in items:
                item_path = os.path.join(BACKUP_DIR, item)
                if os.path.isdir(item_path) and item.startswith("backup_"):
                    stat = os.stat(item_path)
                    debug_info['backup_dirs'].append({
                        'name': item,
                        'size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                    })
        except Exception as e:
            debug_info['error'] = str(e)
    
    return render_template('debug_backup.html', debug_info=debug_info)

@app.route('/api/create-backup', methods=['POST'])
@login_required
def api_create_backup():
    success, message = backup_config()
    return jsonify({
        'success': success,
        'message': message
    })

@app.route('/api/delete-old-backups', methods=['POST'])
@login_required
def api_delete_old_backups():
    try:
        cutoff_date = datetime.now() - timedelta(days=30)
        deleted_count = 0
        
        if os.path.exists(BACKUP_DIR):
            for item in os.listdir(BACKUP_DIR):
                item_path = os.path.join(BACKUP_DIR, item)
                if os.path.isdir(item_path) and item.startswith("backup_"):
                    try:
                        create_time = datetime.fromtimestamp(os.path.getctime(item_path))
                        
                        if create_time < cutoff_date:
                            shutil.rmtree(item_path)
                            deleted_count += 1
                            logging.info(f"Deleted old backup: {item}")
                    except Exception as e:
                        logging.error(f"Error deleting old backup {item}: {e}")
        
        return jsonify({
            'success': True,
            'count': deleted_count,
            'message': f'Deleted {deleted_count} old backups'
        })
    except Exception as e:
        logging.error(f"Error in delete_old_backups: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/api/check-expired-rules', methods=['POST'])
@login_required
def api_check_expired_rules():
    try:
        check_expired_rules()
        return jsonify({
            'success': True,
            'message': 'Expired rules check completed'
        })
    except Exception as e:
        logging.error(f"Error in check_expired_rules: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/api/nftables-status')
@login_required
def api_nftables_status():
    status = check_nftables_status()
    return jsonify(status)

if __name__ == "__main__":
    logging.info("=== Starting nftables Manager application ===")
    init_db()
    
    success, message = save_rules()
    if success:
        logging.info("Default rules applied successfully")
    else:
        logging.error(f"Failed to apply default rules: {message}")
    
    checker_thread = threading.Thread(target=expired_rules_checker, daemon=True)
    checker_thread.start()
    logging.info("Started expired rules checker thread")
    
    app.run(host="0.0.0.0", port=2107, debug=False)