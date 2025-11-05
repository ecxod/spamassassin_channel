#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_channel_cf.py
----------------------
Lieste Regeln aus MySQL (Tabellen: channels, channel_rules, rules),
generiert pro Channel eine .cf-Datei im SpamAssassin-Format,
validiert Syntax mit `spamassassin -D` und gibt Metadaten aus.

Voraussetzungen:
    pip install mysql-connector-python jinja2 pyyaml
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
import yaml
from jinja2 import Environment, FileSystemLoader

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
# Konfiguration laden (YAML)
# --------------------------------------------------------------------------- #
def load_config(config_path: Path) -> Dict[str, Any]:
    """Lade YAML-Konfiguration und führe Basis-Validierung durch."""
    if not config_path.exists():
        log.error("Konfigurationsdatei nicht gefunden: %s", config_path)
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        log.info("Konfiguration geladen: %s", config_path)
        return config
    except Exception as e:
        log.error("Fehler beim Parsen der config.yaml: %s", e)
        sys.exit(1)


# --------------------------------------------------------------------------- #
# Jinja2 Setup (dynamisch aus Config)
# --------------------------------------------------------------------------- #
def setup_jinja(config: Dict[str, Any]) -> Environment:
    template_dir = Path(config["template_dir"])
    if not template_dir.exists():
        log.error("Template-Verzeichnis nicht gefunden: %s", template_dir)
        sys.exit(1)
    return Environment(
        loader=FileSystemLoader(template_dir),
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
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_cf_file(cf_path: Path, sa_bin: str) -> bool:
    cmd = [sa_bin, "-D", "--lint", f"--cf={cf_path}"]
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


def write_cf_file(channel: Dict[str, Any], rules: List[Dict[str, Any]], out_dir: Path, jinja_env: Environment) -> Path:
    template = jinja_env.get_template("channel.cf.j2")
    cf_content = template.render(
        channel=channel,
        rules=rules,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ"),
    )

    cf_path = out_dir / f"{channel['name']}.cf"
    cf_path.write_text(cf_content, encoding="utf-8")
    log.info("CF-Datei geschrieben: %s", cf_path)

    # Hash-Validierung
    for r in rules:
        if r["rule_hash"] != compute_hash(r["rule"]):
            log.warning("Hash-Mismatch für Regel %s", r["rule_name"])

    return cf_path


# --------------------------------------------------------------------------- #
# Hauptlogik
# --------------------------------------------------------------------------- #
def main(channel_id: int | None, config: Dict[str, Any]):
    # Jinja Setup
    jinja_env = setup_jinja(config)

    # Output-Verzeichnis
    out_dir = Path(config["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # MySQL Verbindung
    mysql_cfg = config["mysql"]
    try:
        conn = mysql.connector.connect(**mysql_cfg)
        cursor = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        log.error("MySQL-Verbindung fehlgeschlagen: %s", err)
        sys.exit(1)

    # Channels laden
    cursor.execute(SQL_CHANNELS, (channel_id, channel_id))
    channels = cursor.fetchall()
    if not channels:
        log.error("Kein Channel mit ID %s gefunden.", channel_id)
        sys.exit(1)

    # Verarbeitung
    for ch in channels:
        log.info("Bearbeite Channel: %s (ID=%s)", ch["name"], ch["id"])

        cursor.execute(SQL_RULES_FOR_CHANNEL, (ch["id"],))
        rules = cursor.fetchall()

        if not rules:
            log.warning("Channel %s hat keine aktiven Regeln.", ch["name"])
            continue

        cf_file = write_cf_file(ch, rules, out_dir, jinja_env)

        if not validate_cf_file(cf_file, config["spamassassin_bin"]):
            log.error("Abbruch für Channel %s wegen Lint-Fehlern.", ch["name"])
            continue

        # Archiv + Signatur
        tar_path = out_dir / f"{ch['name']}.tar.bz2"
        subprocess.run(
            ["tar", "-cjf", str(tar_path), "-C", str(out_dir), cf_file.name],
            check=True,
        )
        sig_path = f"{tar_path}.asc"
        subprocess.run(
            ["gpg", "--armor", "--sign", "--default-key", config["gpg_key"], "-o", sig_path, str(tar_path)],
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
        default=Path("config.yaml"),
        help="Pfad zur YAML-Konfigurationsdatei",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    main(args.channel_id, config)