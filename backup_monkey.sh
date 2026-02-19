#!/bin/bash

# Exit on error
set -e

# ==========================================
# CONFIGURATION
# ==========================================
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_NAME="FunkyMonkey_$TIMESTAMP.tar.gz"

# Automatically resolve the project root based on script location
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Directories (Relative to PROJECT_DIR)
SOURCE_DIR="$PROJECT_DIR"
TEMP_WORK_DIR="/tmp/monkey_backup_staging"
SCRIPT_PATH="$PROJECT_DIR/backup_monkey.sh"
LOG_FILE="$PROJECT_DIR/backup.log"

# Remote & Retention
DEST_REMOTE="gdrive:Server Backups/FunkyMonkeyFriday-Backups"
RETENTION_DAYS="30d"

# ==========================================
# FUNCTIONS
# ==========================================

log_msg() {
    echo "$(date): $1" >> "$LOG_FILE"
}

validate_json() {
    # Uses python to check if the JSON structure is valid
    python3 -m json.tool "$1" > /dev/null 2>&1
    return $?
}

# ==========================================
# EXECUTION
# ==========================================

log_msg "Starting Backup..."

# 1. Create a Clean Staging Area
rm -rf "$TEMP_WORK_DIR"
mkdir -p "$TEMP_WORK_DIR"

# 2. Stage verified files
cp "$SCRIPT_PATH" "$TEMP_WORK_DIR/"
cp "$SOURCE_DIR/config.json" "$TEMP_WORK_DIR/"

# 3. Resilient Copy of users.json (The "Hot" File)
cp "$SOURCE_DIR/users.json" "$TEMP_WORK_DIR/users.json"

if validate_json "$TEMP_WORK_DIR/users.json"; then
    log_msg "[OK] JSON Integrity Verified."
else
    log_msg "[WARN] JSON Verification failed (collision detected). Retrying in 2s..."
    sleep 2
    cp "$SOURCE_DIR/users.json" "$TEMP_WORK_DIR/users.json"
    
    if validate_json "$TEMP_WORK_DIR/users.json"; then
        log_msg "[OK] JSON Integrity Verified on retry."
    else
        log_msg "[CRITICAL] JSON is corrupt. Aborting backup."
        rm -rf "$TEMP_WORK_DIR"
        exit 1
    fi
fi

# 4. Create Tarball (Compressed)
# -C changes directory to staging so the tarball doesn't contain /tmp/ pathing
tar -czf "/tmp/$BACKUP_NAME" -C "$TEMP_WORK_DIR" . >> "$LOG_FILE" 2>&1

# 5. Upload to Google Drive
if /usr/bin/rclone copy "/tmp/$BACKUP_NAME" "$DEST_REMOTE"; then
    log_msg "[SUCCESS] Uploaded $BACKUP_NAME"
    
    # Cleanup Remote (Retention Policy)
    /usr/bin/rclone delete "$DEST_REMOTE" --min-age $RETENTION_DAYS 2>/dev/null || true
else
    log_msg "[FAILURE] Upload failed!"
fi

# 6. Cleanup Staging
rm -f "/tmp/$BACKUP_NAME"
rm -rf "$TEMP_WORK_DIR"
