
### Voraussetzungen:

#### Debian install Spamassassin
```sh
sudo apt install spamassassin
```
```sh
pip install mysql-connector-python jinja2
```

### CREATE USER FOR DATABASE
```sql
CREATE USER 'sa_channel'@'localhost' IDENTIFIED BY 'secret';
GRANT USAGE ON *.* TO 'sa_channel'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `sa_channel`.* TO 'sa_channel'@'localhost';
FLUSH PRIVILEGES;
```
### CREATE DATABASE TABLES
```sql
CREATE TABLE `rules` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `rule` MEDIUMTEXT NOT NULL,
    `rule_name` VARCHAR(100) NOT NULL,
    `score` DECIMAL(6,4) NOT NULL DEFAULT 0.0000,
    `sa_version` VARCHAR(20) NOT NULL,
    `author` VARCHAR(100) NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `active` TINYINT(1) NOT NULL DEFAULT 1,
    `status` VARCHAR(20) NOT NULL DEFAULT 'development',
    `description` TEXT,
    `rule_hash` CHAR(64) NOT NULL,
    `test_status` ENUM('untested','passed','failed','skipped') NOT NULL DEFAULT 'untested',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uniq_rule_name_version` (`rule_name`, `sa_version`),
    INDEX `idx_hash` (`rule_hash`),
    INDEX `idx_status_active` (`status`, `active`),
    INDEX `idx_sa_version` (`sa_version`)
)
ENGINE = InnoDB COLLATE = 'utf8mb4_unicode_ci';
```
```sql
CREATE TABLE `channels` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(50) NOT NULL,
    `description` TEXT,
    `is_default` TINYINT(1) NOT NULL DEFAULT 0,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uniq_name` (`name`)
) ENGINE=InnoDB COLLATE='utf8mb4_unicode_ci';
```
```sql
CREATE TABLE `channel_rules` (
    `channel_id` INT UNSIGNED NOT NULL,
    `rule_id` INT UNSIGNED NOT NULL,
    `added_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`channel_id`, `rule_id`),
    FOREIGN KEY (`channel_id`) REFERENCES `channels`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`rule_id`) REFERENCES `rules`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;
```

### Nicht vergessen Public Key auf Webserver legen
```
# {{ channel.cf.j2 }}
channel_key channel@dein-domain.de https://dein-domain.de/channel_pubkey.asc
```

### Projekt tree
```
└── sa_channel
    ├── db
    │   ├── channel_rules.sql
    │   ├── channels.sql
    │   ├── create_user.sql
    │   └── rules.sql
    └── main
        ├── build_and_publish.sh
        ├── config.yaml
        ├── generate_cf.py
        ├── generate_channel_cf.py
        ├── gpg
        │   ├── channel@dein-domain.de.pub  # ← Public Key
        │   ├── channel@dein-domain.de.sec  # ← Secret Key (include in .gitigmore)
        │   ├── channel_pubkey.asc          # ← Public Key (ascii)
        │   └── README.md
        ├── logs
        └── templates
            └── channel.cf.j2
.gitignore
```

