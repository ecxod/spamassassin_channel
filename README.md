
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
        ├── logs
        └── templates
            └── channel.cf.j2
```

