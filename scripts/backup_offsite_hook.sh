#!/usr/bin/env bash
# Offsite backup hook — Phase 10 stub (architecture §70, gap A4/C2)
#
# Called by the daily_backup beat task after pg_dump succeeds.
# In production, replace this stub with a real offsite copy (S3, GCS, rsync, etc.)
#
# Usage: backup_offsite_hook.sh --source-dir <dir> --dest-uri <uri>
#
# Exit codes:
#   0 = success (or stub no-op)
#   1 = usage error
#   2 = copy failed

set -euo pipefail

SOURCE_DIR=""
DEST_URI=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-dir)
            SOURCE_DIR="$2"
            shift 2
            ;;
        --dest-uri)
            DEST_URI="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$SOURCE_DIR" || -z "$DEST_URI" ]]; then
    echo "Usage: $0 --source-dir <dir> --dest-uri <uri>" >&2
    exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "Source directory does not exist: $SOURCE_DIR" >&2
    exit 2
fi

echo "[backup_offsite_hook] STUB: Would copy $SOURCE_DIR to $DEST_URI"
echo "[backup_offsite_hook] Implement real offsite copy here (aws s3 sync, gsutil, rclone, etc.)"

# Example implementations (uncomment and configure for production):
# aws s3 sync "$SOURCE_DIR" "$DEST_URI" --storage-class GLACIER
# gsutil -m rsync -r "$SOURCE_DIR" "$DEST_URI"
# rclone sync "$SOURCE_DIR" "$DEST_URI"

exit 0