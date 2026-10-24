-- Docker 首次初始化时执行（仅在数据卷为空时运行一次）
-- 目的：给自动化测试准备独立库，避免 TEST_DATABASE_URL 误指演示库 hospital
--       （tests/conftest.py 会 DROP 表，指错库会毁掉演示数据）。
-- 演示库 hospital 与账号 hospital_app 由官方镜像的 MYSQL_DATABASE / MYSQL_USER 创建。

CREATE DATABASE IF NOT EXISTS `hospital_test`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON `hospital_test`.* TO 'hospital_app'@'%';
FLUSH PRIVILEGES;
