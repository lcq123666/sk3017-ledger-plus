-- ---------------------------------------------------------------------------
-- SK3017 课程设计 · 个人记账本（收支管理 + 图表统计）
-- 建库建表脚本（MySQL 8.0 / InnoDB / utf8mb4）
-- 执行方式：
--   mysql -uroot -p < database/schema.sql
-- 表结构与 app/models.py 一一对应，可二选一使用：
--   （A）本脚本建表   （B）flask --app run.py init-db 由 ORM 建表
-- ---------------------------------------------------------------------------

CREATE DATABASE IF NOT EXISTS `sk3017_ledger`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `sk3017_ledger`;
SET NAMES utf8mb4;

-- 删除顺序与建表顺序相反，避免外键约束报错
DROP TABLE IF EXISTS `record`;
DROP TABLE IF EXISTS `budget`;
DROP TABLE IF EXISTS `category`;
DROP TABLE IF EXISTS `account`;
DROP TABLE IF EXISTS `user`;

-- ---------------------------------------------------------------------------
-- 1. 用户表
-- ---------------------------------------------------------------------------
CREATE TABLE `user` (
  `id`            INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `username`      VARCHAR(32)  NOT NULL                COMMENT '登录名（唯一）',
  `password_hash` VARCHAR(255) NOT NULL                COMMENT '密码哈希（pbkdf2:sha256，不存明文）',
  `nickname`      VARCHAR(32)  NOT NULL                COMMENT '昵称',
  `email`         VARCHAR(120) DEFAULT NULL            COMMENT '邮箱（可选）',
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- ---------------------------------------------------------------------------
-- 2. 资金账户表
-- ---------------------------------------------------------------------------
CREATE TABLE `account` (
  `id`         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`    INT UNSIGNED NOT NULL                COMMENT '所属用户',
  `name`       VARCHAR(32)  NOT NULL                COMMENT '账户名称，如 支付宝',
  `kind`       VARCHAR(16)  NOT NULL DEFAULT 'cash' COMMENT '账户类型 cash/alipay/wechat/bank',
  `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_account_user_name` (`user_id`, `name`),
  CONSTRAINT `fk_account_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='资金账户表';

-- ---------------------------------------------------------------------------
-- 3. 收支分类表
-- ---------------------------------------------------------------------------
CREATE TABLE `category` (
  `id`         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`    INT UNSIGNED NOT NULL                COMMENT '所属用户',
  `name`       VARCHAR(20)  NOT NULL                COMMENT '分类名称',
  `type`       VARCHAR(8)   NOT NULL DEFAULT 'expense' COMMENT 'expense 支出 / income 收入',
  `icon`       VARCHAR(16)  NOT NULL DEFAULT '💰'   COMMENT '图标（emoji）',
  `color`      VARCHAR(16)  NOT NULL DEFAULT '#6366f1' COMMENT '图表配色',
  `is_default` TINYINT(1)   NOT NULL DEFAULT 0      COMMENT '1=系统预置，不可删除',
  `sort_order` INT          NOT NULL DEFAULT 0      COMMENT '排序权重',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_category_user_name_type` (`user_id`, `name`, `type`),
  KEY `ix_category_user_type` (`user_id`, `type`),
  CONSTRAINT `fk_category_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='收支分类表';

-- ---------------------------------------------------------------------------
-- 4. 记账记录表（核心业务表）
-- ---------------------------------------------------------------------------
CREATE TABLE `record` (
  `id`          INT UNSIGNED  NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`     INT UNSIGNED  NOT NULL                COMMENT '所属用户',
  `amount`      DECIMAL(10,2) NOT NULL                COMMENT '金额（正数，两位小数）',
  `type`        VARCHAR(8)    NOT NULL DEFAULT 'expense' COMMENT 'expense 支出 / income 收入',
  `category_id` INT UNSIGNED  DEFAULT NULL            COMMENT '分类（分类被删后置 NULL）',
  `account_id`  INT UNSIGNED  DEFAULT NULL            COMMENT '账户（账户被删后置 NULL）',
  `record_date` DATE          NOT NULL                COMMENT '记账日期',
  `note`        VARCHAR(200)  DEFAULT NULL            COMMENT '备注',
  `created_at`  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `ix_record_user_date` (`user_id`, `record_date`),
  KEY `ix_record_user_category` (`user_id`, `category_id`),
  KEY `ix_record_record_date` (`record_date`),
  CONSTRAINT `fk_record_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_record_category` FOREIGN KEY (`category_id`) REFERENCES `category` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_record_account` FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记账记录表';

-- ---------------------------------------------------------------------------
-- 5. 月度预算表
-- ---------------------------------------------------------------------------
CREATE TABLE `budget` (
  `id`         INT UNSIGNED  NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`    INT UNSIGNED  NOT NULL                COMMENT '所属用户',
  `year`       INT           NOT NULL                COMMENT '年份',
  `month`      INT           NOT NULL                COMMENT '月份 1~12',
  `amount`     DECIMAL(10,2) NOT NULL DEFAULT 0.00   COMMENT '预算金额',
  `created_at` DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_budget_user_month` (`user_id`, `year`, `month`),
  CONSTRAINT `fk_budget_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_budget_month` CHECK (`month` BETWEEN 1 AND 12)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='月度预算表';

-- 完成提示
SELECT '[OK] sk3017_ledger 建库建表完成' AS result;
