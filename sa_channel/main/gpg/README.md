## GPG-Key erstellen (channel@dein-domain.de)

```bash
# 1. GPG-Keypaar erzeugen (interaktiv)
gpg --full-generate-key

# Wähle:
# - Kind: RSA and RSA (default)
# - Größe: 4096
# - Ablauf: 2y (oder 0 für kein Ablauf)
# - Real name: SpamAssassin Channel
# - Email: channel@dein-domain.de
# - Comment: (leer lassen)
# - Passphrase: starkes Passwort (in config.yaml oder env speichern!)
```

```bash
# 2. Key-ID ermitteln (langes Format)
gpg --list-keys channel@dein-domain.de
#pub rsa4096 2025-11-05 [SC]
#      E4656E8995F290C16B3961A166B48DAB06AB1E55
#uid [ultimate] SpamAssassin Channel <channel@dein-domain.de>
#sub rsa4096 2025-11-05 [E]

#2. Key-ID ermitteln (kurzform)
gpg --list-keys --with-colons channel@dein-domain.de | awk -F: '/^pub:/ {print "0x" substr($5, length($5)-15)}'
# → 0x66B48DAB06AB1E55
```

```bash
# 3. Public Key exportieren (für sa-update-Vertrauen)
gpg --armor --export channel@dein-domain.de > channel_pubkey.asc
```

## Thread 2: Wo wird der Key abgelegt?

```
└── sa_channel
    ├── main
    │   ├── gpg
    │   │   ├── channel@dein-domain.de.sec   # ← Secret Key (NIE committen!)
    │   │   ├── channel@dein-domain.de.pub   # ← Public Key (für Backup)
    │   │   └── channel_pubkey.asc           # ← Für Webserver / sa-update
    │   └── build_and_publish.sh
```

```bash
# Automatisch im Skript (build_and_publish.sh)
mkdir -p main/gpg
gpg --export-secret-keys channel@dein-domain.de > main/gpg/channel@dein-domain.de.sec
gpg --export channel@dein-domain.de > main/gpg/channel@dein-domain.de.pub
```

> **WICHTIG**: `.sec`-Datei **nie** in Git! → `.gitignore`:
> ```
> /main/gpg/*.sec
> /main/gpg/private-keys-v1.d/
> ```

## Thread 3: Bash-Wrapper – Signieren im build_and_publish.sh

```bash
#!/bin/bash
# ...
tar cf channel.tar rules/*.cf
gpg --batch --pinentry-mode loopback --passphrase-file <(echo "$GPG_PASSPHRASE") \
    --local-user channel@dein-domain.de --sign --detach-sign \
    -o channel.tar.bz2.sig channel.tar.bz2
# ...
```

## Thread 4: config.yaml (Auszug)

```yaml
gpg:
  key_id: "0x1234567890ABCDEF"
  email: "channel@dein-domain.de"
  passphrase_env: "GPG_PASSPHRASE"  # export GPG_PASSPHRASE=...
  key_dir: "main/gpg"
```

```txt
└── sa_channel
    ├── db
    │   └── ...
    └── main
        ├── gpg
        │   ├── channel@dein-domain.de.pub
        │   └── channel_pubkey.asc
        ├── build_and_publish.sh
        ├── config.yaml
        └── .gitignore → /main/gpg/*.sec
```

**Nächster Schritt**: Public Key auf Webserver legen → `https://dein-domain.de/channel_pubkey.asc` und in `channel.cf.j2` einbinden:

```jinja2
# {{ channel.cf.j2 }}
channel_key channel@dein-domain.de https://dein-domain.de/channel_pubkey.asc
```