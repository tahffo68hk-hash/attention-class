# P4 DeepSeek Real Provider Pilot — 本地证据目录

对应报告：`docs/P4_DEEPSEEK_REAL_PILOT.md`
Pilot ID：`P4PILOT-20261014T134307+0800`

## 文件清单

| 文件 | 内容 |
|---|---|
| `preflight_dry_run.json` | 零网络彩排的结构化结果：两类出站载荷、白名单、SHA256、字节大小、最坏情况费用 |
| `dry_run_console.log` | 彩排控制台完整输出（24 项检查全 PASS） |
| `api_gate_checks.md` | API 级门禁与业务副作用核验的原始观测 |
| `README.md` | 本索引 |

## 脱敏声明

- **未保存** `Authorization` 请求头、`DEEPSEEK_API_KEY` 或任何密钥取值。
  彩排中进程内使用的占位串在落盘前已被替换为 `<REDACTED>`。
- **未保存**任何原始患者身份数据（姓名、住院证号、诊断、手机号、证件号、地址）。
  出站载荷本身即为数值白名单快照，不含上述任何字段。
- 彩排涉及的患者/床位/住院证均为项目内**虚构演示数据**；`preflight_dry_run.json`
  中的 `reports`/`meta` 亦不含识别性字段（构建器已过滤前缀为 `_` 的本地探针）。
- 每次真实调用若发生，其 provider 请求 ID 未由现有 API 契约透出
  （`deepseek_provider._parse` 未映射 `id` 字段），属已知信息缺口，非本次授权阻塞项。
