-- =====================================================================
-- 系统级初始化脚本（不含任何业务表结构）
-- =====================================================================
-- 说明：
--   本脚本只负责「数据库 + 应用账号」这一层，属于 M0 工程初始化内容。
--   业务数据表结构**不在此定义**，由 Alembic 迁移管理
--   （backend/alembic/versions/），正式表结构待业务设计确认后定稿。
--
-- ⚠️ 本文件是**模板**，只含占位符 __APP_DB_PASSWORD__，不含任何真实口令
--    （本仓库公开，禁止在受版本控制的文件里写入可用凭据）。
--
-- 使用方式（推荐，从 backend/.env 取口令，渲染后再执行）：
--   python scripts/render_sql_init.py --print | \
--     mysql -h 127.0.0.1 -P 3307 -u root -p
--   或渲染到临时文件（/tmp 或本机任意位置，勿提交）：
--   python scripts/render_sql_init.py --out /tmp/init_db.sql
--   mysql -h 127.0.0.1 -P 3307 -u root -p < /tmp/init_db.sql
--
--   渲染器读取顺序：环境变量 APP_DB_PASSWORD → backend/.env 中的
--   DATABASE_URL 口令段。取不到就报错退出，绝不使用默认口令。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `hospital`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 自动化测试专用库（并发与状态流转测试在真实 MySQL 上执行）
CREATE DATABASE IF NOT EXISTS `hospital_test`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 应用账号：仅用于本地原型开发，生产环境请使用独立强口令与最小权限
CREATE USER IF NOT EXISTS 'hospital_app'@'%' IDENTIFIED BY '__APP_DB_PASSWORD__';

GRANT ALL PRIVILEGES ON `hospital`.*      TO 'hospital_app'@'%';
GRANT ALL PRIVILEGES ON `hospital_test`.* TO 'hospital_app'@'%';

FLUSH PRIVILEGES;
