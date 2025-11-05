#!/usr/bin/env python3
"""
generate_cf.py
---------------
Liest aus MySQL:
  - channels
  - rules (via channel_rules)
Generiert pro Channel eine *.cf-Datei via Jinja2-Template.
Schreibt in <output_dir>/<channel_name>.cf
"""

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict

import mysql.connector
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("generate_cf")

# --------------------------------------------------------------------------- #
# Argumente
# --------------------------------------------------------------------------- #
parser = argparse.ArgumentParser(description="Generate SpamAssassin channel .cf files")
parser.add_argument(
    "--config",
    default="config.yaml",
    help="Pfad zur config.yaml (DB-Zugang, Pfade, etc.)",
)
parser.add_argument(
    "--channel",
    type=str,
    help="Nur diesen Channel generieren (Name, wie in `channels.name`)",
)
parser.add_argument(
    "--output-dir",
    default="output",
    help="Zielverzeichnis für *.cf-Dateien",
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Nur Log-Ausgabe, keine Dateien schreiben",
)
args = parser.parse_args()

# --------------------------------------------------------------------------- #
# Config laden
# --------------------------------------------------------------------------- #
try:
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
except Exception as e:
    log.error("Kann config.yaml nicht laden: %s", e)
    sys.exit(1)

DB_CFG = cfg.get("mysql", {})
TEMPLATE_DIR = Path(cfg.get("templates_dir", "templates"))
OUTPUT_DIR = Path(args.output_dir)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Jinja2 Environment
# --------------------------------------------------------------------------- #
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

# --------------------------------------------------------------------------- #
# DB-Verbindung
# --------------------------------------------------------------------------- #
try:
    cnx = mysql.connector.connect(**DB_CFG)
    cursor = cnx.cursor(dictionary=True)
except mysql.connector.Error as err:
    log.error("MySQL-Verbindung fehlgeschlagen: %s", err)
    sys.exit(1)

# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def compute_rule_hash(rule_text: str) -> str:
    """SHA-256 des reinen Regel-Textes (wie in DB gespeichert)."""
    return hashlib.sha256(rule_text.encode("utf-8")).hexdigest()


def fetch_channels() -> List[Dict]:
    query = """
        SELECT id, name, description, is_default
        FROM channels
        WHERE 1=1
    """
    if args.channel:
        query += " AND name = %(name)s"
    cursor.execute(query, {"name": args.channel} if args.channel else {})
    return cursor.fetchall()


def fetch_rules_for_channel(channel_id: int) -> List[Dict]:
    query = """
        SELECT r.id, r.rule_name, r.rule, r.score, r.sa_version,
               r.author, r.description, r.rule_hash, r.test_status
        FROM rules r
        JOIN channel_rules cr ON r.id = cr.rule_id
        WHERE cr.channel_id = %(channel_id)s
          AND r.active = 1
          AND r.status = 'production'   -- nur produktive Regeln
        ORDER BY r.rule_name
    """
    cursor.execute(query, {"channel_id": channel_id})
    return cursor.fetchall()


# --------------------------------------------------------------------------- #
# Hauptlogik
# --------------------------------------------------------------------------- #
channels = fetch_channels()
if not channels:
    log.warning("Keine Channels gefunden (Filter: %s)", args.channel or "alle")
    sys.exit(0)

for chan in channels:
    channel_id = chan["id"]
    channel_name = chan["name"]
    log.info("Generiere .cf für Channel '%s' (ID %s)", channel_name, channel_id)

    rules = fetch_rules_for_channel(channel_id)
    log.info("  → %d aktive produktive Regeln", len(rules))

    # Jinja-Variablen
    context = {
        "channel": chan,
        "rules": rules,
        "generated_at": cnx.get_server_info(),  # optional: UTC-Timestamp
    }

    # Template rendern
    template = jinja_env.get_template("channel.cf.j2")
    rendered = template.render(**context)

    # Ziel-Datei
    out_file = OUTPUT_DIR / f"{channel_name}.cf"

    if args.dry_run:
        log.info("  [DRY-RUN] %s würde geschrieben werden", out_file)
        continue

    try:
        out_file.write_text(rendered, encoding="utf-8")
        log.info("  → %s geschrieben (%d Bytes)", out_file, out_file.stat().st_size)
    except Exception as e:
        log.error("  Fehler beim Schreiben von %s: %s", out_file, e)

# --------------------------------------------------------------------------- #
# Aufräumen
# --------------------------------------------------------------------------- #
cursor.close()
cnx.close()
log.info("Fertig.")