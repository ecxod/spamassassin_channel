CREATE TABLE `channel_rules` (
    `channel_id` INT UNSIGNED NOT NULL,
    `rule_id` INT UNSIGNED NOT NULL,
    `added_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`channel_id`, `rule_id`),
    FOREIGN KEY (`channel_id`) REFERENCES `channels`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`rule_id`) REFERENCES `rules`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;