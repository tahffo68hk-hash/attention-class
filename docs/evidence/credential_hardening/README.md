# 凭据治理与 Pilot 前置检查 —— 本地证据目录

对应报告：`docs/P4_CREDENTIAL_HARDENING.md`

## 文件清单

| 文件 | 内容 |
|---|---|
| `exposure_audit_before.txt` | **修复前**：公开边界 `origin/main` 顶端树里的凭据取值清单（只列指纹/长度/位置） |
| `exposure_audit_after.txt` | **修复后**：工作区跟踪文件的凭据位现状（应只剩占位符） |
| `no_leak_verification.txt` | **决定性核查**：把公开历史中的每个真实取值逐个取出，再在工作区搜一遍 |
| `rotation_verification.txt` | 轮换验证：旧口令失效 / 新口令可用 / 旧密钥签发的 JWT 被拒绝 / 应用可真实查询 |
| `new_secrets_gitignored.txt` | 轮换后的新取值只存在于 gitignored 文件（受版本控制内容中零命中） |
| `pilot_concurrency_after.txt` | Pilot 授权闸门并发探针（计数闸门 + 预算闸门）修复后结果 |

## 脱敏声明

- 本目录**不含任何明文口令或密钥**，只含 SHA256 指纹、长度与文件位置。
- 核查脚本不把取值写入仓库，仅用于本机一次性核对。
- `.env`（根目录与 `backend/`）均被 `.gitignore` 排除，轮换后的新取值只存在于本机。
