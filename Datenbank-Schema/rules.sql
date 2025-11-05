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
COLLATE = 'utf8mb4_unicode_ci'
ENGINE = InnoDB;
