#!/bin/bash
# =============================================================================
# build_and_publish.sh
# --------------------
# Vollautomatischer Build- und Publish-Prozess für SpamAssassin-Channels
#   1. Generiert .cf via Python
#   2. Packt + signiert
#   3. Lädt auf Webserver
#   4. Aktualisiert DNS TXT
#   5. Trigert sa-update auf Testsystemen
#
# Aufruf: ./build_and_publish.sh [config.yaml] [channel_id]
# =============================================================================

set -euo pipefail

# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

die() {
    log "FATAL: $*" >&2
    exit 1
}

# Lockfile
LOCKFILE="/var/run/sa_channel_build.lock"
if [ -f "$LOCKFILE" ]; then
    die "Ein weiterer Build läuft bereits (Lockfile: $LOCKFILE)"
fi
trap 'rm -f "$LOCKFILE"' EXIT
echo $$ > "$LOCKFILE"

# --------------------------------------------------------------------------- #
# Argumente
# --------------------------------------------------------------------------- #
CONFIG_FILE="${1:-config.yaml}"
CHANNEL_ID="${2:-}"

[[ -f "$CONFIG_FILE" ]] || die "Config nicht gefunden: $CONFIG_FILE"

log "Starte Build mit Config: $CONFIG_FILE"
[[ -n "$CHANNEL_ID" ]] && log "Channel-ID: $CHANNEL_ID"

# --------------------------------------------------------------------------- #
# Config laden (nur für Bash relevante Teile)
# --------------------------------------------------------------------------- #
BUILD_DIR=$(yq e '.output_dir' "$CONFIG_FILE")
DOMAIN=$(yp e '.domain' "$CONFIG_FILE")
WEB_ROOT=$(yq e '.web_root' "$CONFIG_FILE")
GPG_KEY=$(yq e '.gpg_key' "$CONFIG_FILE")
DNS_ZONE=$(yq e '.dns_zone_file // ""' "$CONFIG_FILE")
TEST_HOSTS=$(yq e '.test_hosts // [] | join(" ")' "$CONFIG_FILE")

[[ -d "$BUILD_DIR" ]] || mkdir -p "$BUILD_DIR"
[[ -d "$WEB_ROOT" ]] || die "Web-Root nicht gefunden: $WEB_ROOT"

# --------------------------------------------------------------------------- #
# 1. Python: .cf generieren
# --------------------------------------------------------------------------- #
log "Starte generate_channel_cf.py"
python3 generate_channel_cf.py --config "$CONFIG_FILE" ${CHANNEL_ID:+--channel-id "$CHANNEL_ID"}

# --------------------------------------------------------------------------- #
# 2. Archive finalisieren + Signieren
# --------------------------------------------------------------------------- #
cd "$BUILD_DIR"

for cf in *.cf; do
    [[ -f "$cf" ]] || continue
    channel="${cf%.cf}"
    tarball="${channel}.tar.bz2"
    sig="${tarball}.asc"

    log "Erstelle Archiv: $tarball"
    tar -cjf "$tarball" "$cf" || die "tar fehlgeschlagen"

    log "Signiere mit GPG: $sig"
    gpg --batch --yes --armor --local-user "$GPG_KEY" --output "$sig" --detach-sign "$tarball" \
        || die "GPG-Signatur fehlgeschlagen"

    # Channel-Info
    echo "channel: $channel" > "${channel}.info"
    echo "built: $(date -u)" >> "${channel}.info"
    echo "rules: $(grep -c '^score ' "$cf")" >> "${channel}.info"
done

# --------------------------------------------------------------------------- #
# 3. Upload zum Webserver
# --------------------------------------------------------------------------- #
log "Kopiere Artefakte nach $WEB_ROOT"
rsync -av --delete-after "$BUILD_DIR"/ *.tar.bz2 *.asc *.info "$WEB_ROOT"/ \
    || die "rsync fehlgeschlagen"

# --------------------------------------------------------------------------- #
# 4. DNS TXT Record aktualisieren (optional)
# --------------------------------------------------------------------------- #
if [[ -n "$DNS_ZONE" && -f "$DNS_ZONE" ]]; then
    log "Aktualisiere DNS TXT Record"
    SERIAL=$(grep -oP '\d{10}' "$DNS_ZONE" | head -1)
    NEW_SERIAL=$(( SERIAL + 1 ))
    TIMESTAMP=$(date +%Y%m%d%H)

    # Einfaches Update-Skript (kann erweitert werden)
    cat > /tmp/nsupdate.txt <<EOF
server 127.0.0.1
zone $DOMAIN
update delete _sa-channel.$DOMAIN. TXT
update add _sa-channel.$DOMAIN. 3600 TXT "v=sa1; t=$(date +%s); s=$NEW_SERIAL"
send
EOF
    nsupdate /tmp/nsupdate.txt || log "nsupdate fehlgeschlagen (ignoriert)"
    rm -f /tmp/nsupdate.txt
fi

# --------------------------------------------------------------------------- #
# 5. sa-update auf Testsystemen triggern
# --------------------------------------------------------------------------- #
if [[ -n "$TEST_HOSTS" ]]; then
    log "Trigger sa-update auf Test-Hosts: $TEST_HOSTS"
    for host in $TEST_HOSTS; do
        log "→ $host"
        ssh -o BatchMode=yes "$host" "sa-update --refresh --channel $DOMAIN" || log "Warnung: sa-update auf $host fehlgeschlagen"
    done
fi

# --------------------------------------------------------------------------- #
# Abschluss
# --------------------------------------------------------------------------- #
log "Build & Publish erfolgreich abgeschlossen!"
log "Verfügbar unter: https://$DOMAIN/"