CREATE TABLE `demo_order` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'primary id',
  `period` varchar(50) NOT NULL COMMENT 'period',
  `amount` decimal(18,2) DEFAULT NULL COMMENT 'amount',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  PRIMARY KEY (`id`),
  KEY `idx_demo_order_period` (`period`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='demo order table';
