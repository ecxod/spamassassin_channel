CREATE USER 'sa_channel'@'localhost' IDENTIFIED BY 'secret';
GRANT USAGE ON *.* TO 'sa_channel'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `sa_channel`.* TO 'sa_channel'@'localhost';
FLUSH PRIVILEGES;