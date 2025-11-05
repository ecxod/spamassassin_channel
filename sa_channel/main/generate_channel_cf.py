#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_channel_cf.py
----------------------
Liest Regeln aus MySQL (Tabellen: channels, channel_rules, rules),
generiert pro Channel eine .cf-Datei im SpamAssassin-Format,
validiert Syntax mit `spamassassin -D` und gibt Metadaten aus.

Voraussetzungen:
    pip install mysql-connector-python jinja2
"""

import argparse
import hashlib
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import mysql.connector
from jinja2 import Environment, FileSystemLoader

# --------------------------------------------------------------------------- #
# Konfiguration
# --------------------------------------------------------------------------- #
DEFAULT_CONFIG = {
    "mysql": {
        "host": "localhost",
        "user": "sa_channel",
        "password": "secret",
        "database": "spamassassin_channel",
        "port": 3306,
    },
    "output_dir": "/var/lib/sa-channel/build",
    "template_dir": "templates",
    "spamassassin_bin": "/usr/bin/spamassassin",
    "gpg_key": "channel@dein-domain.de",
    "web_root": "/var/www/sa-channel",
    "dns_zone_file": "/etc/bind/db.dein-channel.de",  # optional
}

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Jinja2 Setup
# --------------------------------------------------------------------------- #
jinja_env = Environment(
    loader=FileSystemLoader(DEFAULT_CONFIG["template_dir"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

# --------------------------------------------------------------------------- #
# Datenbank-Abfragen
# --------------------------------------------------------------------------- #
SQL_CHANNELS = """
SELECT id, name, description, is_default
FROM channels
WHERE id = %s OR %s IS NULL;
"""

SQL_RULES_FOR_CHANNEL = """
SELECT r.id, r.rule_name, r.rule, r.score, r.sa_version,
       r.author, r.description, r.rule_hash, r.test_status
FROM rules r
JOIN channel_rules cr ON r.id = cr.rule_id
WHERE cr.channel_id = %s
  AND r.active = 1
  AND r.status = 'production'
ORDER BY r.rule_name;
"""

# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def compute_hash(content: str) -> str:
    """SHA-256 Hash des Regel-Inhalts (wie in DB gespeichert)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_cf_file(cf_path: Path) -> bool:
    """Führe `spamassassin -D <file>` aus und prüfe auf Syntax-Fehler."""
    cmd = [DEFAULT_CONFIG["spamassassin_bin"], "-D", "--lint", f"--cf={cf_path}"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=30
        )
        if result.returncode != 0:
            log.error("Lint-Fehler in %s:\n%s", cf_path.name, result.stderr)
            return False
        log.info("Lint OK: %s", cf_path.name)
        return True
    except Exception as e:
        log.exception("Fehler beim Lint von %s: %s", cf_path.name, e)
        return False


def write_cf_file(channel: Dict[str, Any], rules: List[Dict[str, Any]], out_dir: Path):
    """Erzeuge .cf-Datei mit Jinja2-Template."""
    template = jinja_env.get_template("channel.cf.j2")
    cf_content = template.render(
        channel=channel,
        rules=rules,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ"),
    )

    cf_path = out_dir / f"{channel['name']}.cf"
    cf_path.write_text(cf_content, encoding="utf-8")
    log.info("CF-Datei geschrieben: %s", cf_path)

    # Hash prüfen (wie in DB)
    computed = compute_hash(cf_content)
    for r in rules:
        if r["rule_hash"] != compute_hash(r["rule"]):
            log.warning("Hash-Mismatch für Regel %s", r["rule_name"])

    return cf_path


# --------------------------------------------------------------------------- #
# Hauptlogik
# --------------------------------------------------------------------------- #
def main(channel_id: int | None):
    # 1. MySQL Verbindung
    try:
        conn = mysql.connector.connect(**DEFAULT_CONFIG["mysql"])
        cursor = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        log.error("MySQL-Verbindung fehlgeschlagen: %s", err)
        sys.exit(1)

    # 2. Channel(s) auswählen
    cursor.execute(SQL_CHANNELS, (channel_id, channel_id))
    channels = cursor.fetchall()
    if not channels:
        log.error("Kein Channel mit ID %s gefunden.", channel_id)
        sys.exit(1)

    out_dir = Path(DEFAULT_CONFIG["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # 3. Für jeden Channel .cf generieren
    for ch in channels:
        log.info("Bearbeite Channel: %s (ID=%s)", ch["name"], ch["id"])

        cursor.execute(SQL_RULES_FOR_CHANNEL, (ch["id"],))
        rules = cursor.fetchall()

        if not rules:
            log.warning("Channel %s hat keine aktiven Regeln.", ch["name"])
            continue

        cf_file = write_cf_file(ch, rules, out_dir)

        # 4. Syntax-Check
        if not validate_cf_file(cf_file):
            log.error("Abbruch für Channel %s wegen Lint-Fehlern.", ch["name"])
            continue

        # 5. Optional: tar.bz2 + GPG Signatur (Vorschau)
        tar_path = out_dir / f"{ch['name']}.tar.bz2"
        subprocess.run(
            ["tar", "-cjf", str(tar_path), "-C", str(out_dir), cf_file.name],
            check=True,
        )
        subprocess.run(
            ["gpg", "--armor", "--sign", "--default-key", DEFAULT_CONFIG["gpg_key"], "-o", f"{tar_path}.asc", str(tar_path)],
            check=True,
        )
        log.info("Archiv + Signatur: %s + .asc", tar_path.name)

    cursor.close()
    conn.close()
    log.info("Generierung abgeschlossen.")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SpamAssassin-Channel .cf-Dateien aus MySQL generieren"
    )
    parser.add_argument(
        "--channel-id",
        type=int,
        help="ID des zu generierenden Channels (optional: alle, wenn leer)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default="config.yaml",
        help="Pfad zur YAML-Konfigurationsdatei (optional)",
    )
    args = parser.parse_args()

    # TODO: YAML-Config laden und DEFAULT_CONFIG überschreiben
    main(args.channel_id)