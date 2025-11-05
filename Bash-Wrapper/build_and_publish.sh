#!/bin/bash
# =============================================================================
# build_and_publish.sh
# Bash-Wrapper für den kompletten Build- & Publish-Prozess des SA-Channels
# Aufruf: ./build_and_publish.sh [--dry-run] [--channel <name>] [--force]
# =============================================================================

set -euo pipefail

# --- Konfiguration -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/generate_cf.py"
CONFIG_FILE="${SCRIPT_DIR}/config.yaml"
LOG_FILE="${SCRIPT_DIR}/logs/build_$(date +%Y%m%d_%H%M%S).log"

# Default-Werte
DRY_RUN=0
FORCE=0
CHANNEL_NAME=""

# --- Logging -----------------------------------------------------------------
log() { echo -e "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

# --- Argumente parsen --------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=1; shift ;;
        --force)   FORCE=1; shift ;;
        --channel) CHANNEL_NAME="$2"; shift 2 ;;
        -h|--help)
            cat <<EOF
Usage: $0 [OPTION...]
  --dry-run          Nur Simulation, keine Änderungen
  --force            Überspringt Tests bei Fehlern
  --channel <name>   Spezifischer Channel (default: alle aktiven)
EOF
            exit 0 ;;
        *) log "Unbekannte Option: $1"; exit 1 ;;
    esac
done

mkdir -p "$(dirname "$LOG_FILE")"

# --- Python-CF-Generierung ---------------------------------------------------
log "Starte CF-Generierung via Python..."
if [[ $DRY_RUN -eq 1 ]]; then
    python3 "$PYTHON_SCRIPT" --config "$CONFIG_FILE" --dry-run ${CHANNEL_NAME:+--channel "$CHANNEL_NAME"}
else
    python3 "$PYTHON_SCRIPT" --config "$CONFIG_FILE" ${CHANNEL_NAME:+--channel "$CHANNEL_NAME"}
fi

# --- SpamAssassin-Test (spamassassin -D) --------------------------------------
log "Führe SpamAssassin-Debug-Tests durch..."
BUILD_DIR=$(yq e '.build.output_dir' "$CONFIG_FILE")
for cf in "$BUILD_DIR"/*.cf; do
    log "Teste: $cf"
    if ! spamassassin -D < /dev/null 2>"${cf}.test.log" | grep -q "debug: "; then
        log "FEHLER beim Parsen von $cf"
        [[ $FORCE -eq 0 ]] && exit 1
    fi
    # Optional: Ham/Spam-Testsets
    if [[ -d "${BUILD_DIR}/tests" ]]; then
        sa-learn --spam "${BUILD_DIR}/tests/spam/" || true
        sa-learn --ham  "${BUILD_DIR}/tests/ham/"  || true
        spamassassin -t "${BUILD_DIR}/tests/spam/"*.eml > "${cf}.spamtest.log" 2>&1
        spamassassin -t "${BUILD_DIR}/tests/ham/"*.eml  > "${cf}.hamtest.log"  2>&1
    fi
done

# --- Tar.bz2 packen -----------------------------------------------------------
log "Erstelle tar.bz2-Archive..."
CHANNEL_ID=$(mysql -NBe "SELECT id FROM channels WHERE name='$CHANNEL_NAME'" spamassassin_db)
VERSION=$(date +%Y%m%d.%H%M)
TARFILE="${BUILD_DIR}/channel_${CHANNEL_ID}_${VERSION}.tar.bz2"

tar -cjf "$TARFILE" -C "$BUILD_DIR" $(ls "$BUILD_DIR"/*.cf | xargs -n1 basename)

# --- GPG-Signatur -------------------------------------------------------------
log "Signiere Archiv mit GPG..."
GPG_KEY=$(yq e '.gpg.key_id' "$CONFIG_FILE")
gpg --local-user "$GPG_KEY" --armor --detach-sign "$TARFILE"
log "Signatur: ${TARFILE}.asc"

# --- Upload auf Webserver -----------------------------------------------------
log "Lade auf Webserver hoch..."
RSYNC_TARGET=$(yq e '.publish.rsync_target' "$CONFIG_FILE")
rsync -avz --progress "$TARFILE" "${TARFILE}.asc" "$RSYNC_TARGET/"

# --- DNS TXT Record aktualisieren ---------------------------------------------
log "Aktualisiere DNS TXT-Record..."
DNS_ZONE=$(yq e '.dns.zone' "$CONFIG_FILE")
DNS_HOST=$(yq e '.dns.host' "$CONFIG_FILE")
TXT_VALUE="v=spf1 include:_spf.${DNS_HOST} ~all||sa-channel=${VERSION}"

if [[ $DRY_RUN -eq 0 ]]; then
    nsupdate <<EOF
server $(yq e '.dns.server' "$CONFIG_FILE")
zone $DNS_ZONE
update delete _sa-channel.$DNS_HOST. TXT
update add _sa-channel.$DNS_HOST. 300 TXT "$TXT_VALUE"
send
EOF
    log "DNS TXT aktualisiert: _sa-channel.$DNS_HOST"
else
    log "DRY-RUN: Würde DNS TXT setzen → $TXT_VALUE"
fi

# --- Abschluss ---------------------------------------------------------------
log "Build & Publish abgeschlossen!"
log "Channel: $CHANNEL_NAME | Version: $VERSION"
log "Archiv: $TARFILE"
[[ $DRY_RUN -eq 1 ]] && log "DRY-RUN: Keine Änderungen vorgenommen."

exit 0