-- =====================================================================
-- 系统级初始化脚本（不含任何业务表结构）
-- =====================================================================
-- 说明：
--   本脚本只负责「数据库 + 应用账号」这一层，属于 M0 工程初始化内容。
--   业务数据表结构**不在此定义**，由 Alembic 迁移管理
--   （backend/alembic/versions/），正式表结构待业务设计确认后定稿。
--
-- 使用（本地 MySQL 8）：
--   mysql -h 127.0.0.1 -P 3307 -u root -p < sql/init/00_create_database.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `hospital`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 自动化测试专用库（并发与状态流转测试在真实 MySQL 上执行）
CREATE DATABASE IF NOT EXISTS `hospital_test`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 应用账号：仅用于本地原型开发，生产环境请使用独立强口令与最小权限
CREATE USER IF NOT EXISTS 'hospital_app'@'%' IDENTIFIED BY 'hospital_pwd_2026';

GRANT ALL PRIVILEGES ON `hospital`.*      TO 'hospital_app'@'%';
GRANT ALL PRIVILEGES ON `hospital_test`.* TO 'hospital_app'@'%';

FLUSH PRIVILEGES;
