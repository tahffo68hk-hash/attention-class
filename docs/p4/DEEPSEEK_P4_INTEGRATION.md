# Attention is all you need — P4 DeepSeek 真实 AI 接入（代码候选）

## 交付事实

基线：用户报告的 P3 Final Gate，HEAD `f318058`；当前包通过在 ChatGPT 持有的 P1.5/P2.5 Full Source 上应用 P3 公开补丁重建候选基线制作，**尚未检查 Windows 上的最终工作树**。本轮只修改辅助解释服务、API、配置、两张 Vue 页面和测试。未改分配事务、五维评分、MySQL 迁移、床位状态及优化目标。

- 默认使用确定性规则（`mode=rules`），不产生任何请求费用。
- 单床：`POST /api/v1/assistant/explain`，`mode=llm` 时调用 DeepSeek。
- 整批：`POST /api/v1/assistant/explain-plan`，`mode=llm` 时只将**聚合指标**交给 DeepSeek，床位 ID/住院证 ID/患者姓名绝不外传。
- 配置状态：`GET /api/v1/assistant/provider-status`，只暴露是否启用、模型名、是否需要确认，不暴露密钥。
- 后端固定真实服务 `https://api.deepseek.com/chat/completions`，默认模型 `deepseek-flash`，JSON 模式+非思考模式（限制输出 500 tokens）；遇到无效 JSON、非正常 finish_reason、限流、余额不足或超时，返回中文错误，不假装是成功的模型结果，不自动重试。
- AI 输出始终标为 `AI_DRAFT_REVIEW_REQUIRED`，由人工复核；不能改写硬约束或写入床位分配。
- 显示模型、真实输入/输出 token、耗时；费用只支持**可配置的人民币估算**，不是账单。官方峰谷价格会变化，未配置费率时返回 `null`。
- 真实调用成功/业务异常记录操作审计，不保存原始模型输入、原始输出或密钥。

## 生产与本地配置

在 **`backend/.env`** 设置（不能把密钥写进 `.env.example`、源码、前端或聊天）：

```dotenv
DEEPSEEK_EXTERNAL_ENABLED=false
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT_SECONDS=15
DEEPSEEK_MAX_OUTPUT_TOKENS=500
# 费用估算（可选；参考当次 DeepSeek 官方账单费率）
DEEPSEEK_INPUT_MISS_CNY_PER_M=
DEEPSEEK_INPUT_HIT_CNY_PER_M=
DEEPSEEK_OUTPUT_CNY_PER_M=
```

API 密钥通过 DeepSeek 官方平台申请：<https://platform.deepseek.com/>。确认实际费用预算及服务可用后，由用户在本地填入密钥并将 `DEEPSEEK_EXTERNAL_ENABLED=true`，重启后端。需要在独立模拟数据上、已登录的管理员/护士页面选择“DeepSeek 实时生成”，勾选一次性确认，再点击生成。此步**会真实对外发送结构化摘要并可能扣费**，不得由 Agent 在未获明确付费授权时自动执行。

建议 Pilot 顺序：

1. 启动原有 MySQL 3307 / FastAPI 8000 / Vue 5173；先验 `GET /assistant/provider-status` 默认 `enabled:false`，点击规则解释无外部网络调用。
2. 只在确认预算和密钥后开启；确认 `enabled:true`，用虚构患者的一张有效候选床位执行 **一次** DeepSeek 解释。检查响应 `provider=deepseek, real_ai=true, status=AI_DRAFT_REVIEW_REQUIRED`、Token 与审计。不要提交真实患者信息。
3. 同样以模拟数据执行 **一次**整批方案解释；验证模型只看到成功人数、优先级、总评分、算法名称等聚合数据，前端显示“待人工核对”，不自动创建分配记录。
4. 故意测试无密钥/无确认/网络错误（以 Mock 为主），必须拒绝或返回安全错误；密钥不进入浏览器请求和日志。
5. 结束时把 `DEEPSEEK_EXTERNAL_ENABLED=false` 作为默认操作状态，记录实际 provider/model/token/费用/日志 ID/前后端结果；必要时在 DeepSeek 平台核对实际账单。

## 与现有接口兼容

- 旧单床 `mode=rules` 默认行为不变；`mode=llm` 由旧泛用模型切换为 DeepSeek 专用服务。老 `ASSISTANT_*` 环境变量仍被配置类接收，但**不会触发 DeepSeek 调用**；只认新的 `DEEPSEEK_*` 配置。
- 旧 `/assistant/explain-plan` 不带 mode 的请求继续使用规则解释；增加可选 `mode` 和 `confirm_external_call`。
- 两张 Vue 候选页面可作改动参考，但本地已验收前端必须**逐段合并，不能覆盖**。
- 本轮 **没有新迁移**，P3 的 `f318058` 和此前历史分配应该保留。

## 已验证与待验证

- 当前容器：`pytest` 纯函数/SQLite/HTTP TestClient：**107/107 PASS**；包含新增 P4 模拟 HTTP 及 P3 12 项回归。Python compile PASS；OpenAPI 路由数 37。
- DeepSeek 模拟响应验证了请求体、域名、JSON 结构、无授权不发网络请求、隐私白名单、失败脱敏和费用估算。
- TypeScript SFC `<script>` 语法：node/TypeScript 解析 PASS。
- 由于本环境不具有用户的 MySQL 3307、本机前端和 DeepSeek 密钥，**没有执行真实收费调用、正式 MySQL 测试、Vue 完整构建、浏览器 E2E 或 Docker**。以上必须在 Windows 环境补验，不得将本报告当成 P4_FINAL_GATE=PASS。

## 测试命令（Windows；在现有隔离项目内）

```powershell
cd 'E:\Attention is all you need\backend'
python -m pytest -q tests_p4 tests_p1p2 tests_p3 tests_m1_local tests_p15 tests_p25
# 后端 MySQL 套件可能删除并重建测试库全部表；仅在确认 hospital_test 可销毁后执行！
python -m pytest -q tests
cd ..\frontend
npm run build
```

## 正式源码来源

DeepSeek 官方文档：
- API 基本配置：<https://api-docs.deepseek.com/zh-cn/>
- Chat Completions：<https://api-docs.deepseek.com/api/create-chat-completion/>
- JSON 模式：<https://api-docs.deepseek.com/guides/json_mode/>
- 模型与价格：<https://api-docs.deepseek.com/quick_start/pricing/>

以上约束用于学校教学**虚构数据**；不是已验证的真实临床部署能力。
