# 小红书接口层 API 指南

本文解释 `openapi/openapi.base.yaml` 背后的接口契约。OpenAPI 文件是接口形状的
事实来源；本文补充 OpenAPI 不擅长表达的流程规则。

## 目标

- 提供 API-only 的小红书能力服务。
- 保持接口层足够通用，可被 MCP 客户端、应用后端、定时任务和未来适配器复用。
- 暴露底层原子工具，而不是高层业务流程。
- 第一版正式接口不包含 DOM 能力。

## Session 模型

session 是一个长期存在的、隔离的小红书身份容器。

每个 session 只拥有一个浏览器 profile 目录。不同 session 永远不共享 profile
目录。复用浏览器 profile 意味着复用同一个 `session_id`。

所有 `session_id` 和 profile 都由接口层按默认环境生成。登录状态、当前搜索结果、
当前帖子上下文和评论上下文只在当前服务进程内有效，程序重启后会重置。接口层会在需要时从
`session.json` 和 profile 继续执行操作。调用方只负责保存和复用 `session_id`，
不指定稳定名称，也不直接接触文件路径。

## 绑定模型

`session_id` 是资源 ID，不是占用凭证。

普通应用可以通过以下接口查询 session 列表，用于发现可复用 session、查看占用状态
和协调工作流：

```text
GET /v1/sessions
```

列表接口不会返回 `user_data_dir`、token、cookie、原始诊断或其他敏感运行信息。

调用方在改变 session 状态或抓取数据前，必须先绑定 session：

```text
create_session -> session_id
bind_session(session_id) -> token
operation(session_id, token, ...)
unbind_session(session_id, token)
```

规则：

- 一个 session 同一时刻最多只有一个有效 token。
- token 没有 TTL。
- session 会一直被占用，直到持有者主动解绑，或管理端强制解绑。
- 公开写操作和抓取操作必须携带 `session_id + token`。
- 纯状态查询可以接受可选 token，用于日志与追踪。

## 登录

HTTP 层只暴露一个登录动作接口：

```text
POST /v1/sessions/{session_id}/login
```

请求体中的 `action` 选择具体行为：

- `cookie`：导入 cookie 到当前 session profile。
- `qrcode`：启动或继续二维码登录流程，并返回当前 challenge。
- `phone_start`：启动手机号登录并发送验证码。
- `phone_submit`：提交手机号验证码。

登录状态通过独立查询接口获取：

```text
GET /v1/sessions/{session_id}/login/status
```

这是纯查询接口，token 可选。

二维码登录可能出现多轮 challenge。例如普通登录二维码扫码成功后，平台仍可能要求
二次安全扫码。应用层应以 `login/status` 返回的最新 `challenge.challenge_id` 和
`challenge.sequence` 为准；只要它们发生变化，就刷新展示新的二维码。

典型状态：

- `waiting_qr_scan` + `required_action=scan_qr`：展示当前二维码，等待扫码。
- `waiting_qr_confirm` + `required_action=confirm_qr`：已扫码，等待手机端确认。
- 新的 `challenge.type=security_qr` 且 `sequence` 增加：展示第二个二维码。
- `ready` + `required_action=none`：登录完成。

## 严格当前位置模式

接口层以 session 内部的当前位置为准。

搜索会记录当前搜索结果中的 `note_id`。通过当前搜索结果中的 `note_id` 或 xsec
参数打开帖子，会切换当前帖子上下文。
评论操作只能作用于当前帖子上下文。

一旦切换到新帖子，旧帖子的根评论上下文立即失效。

这能避免“已经打开 B 帖子，却误用 A 帖子的 `comment_id` 继续抓评论”这类错误。

## 上下文校验

接口层不对外返回内部句柄。应用层直接使用平台原始 id：

- `note_id`
- `comment_id`

runtime 在内存中记录当前搜索结果和当前帖子评论结果。传入的 id 不属于当前上下文时，
接口返回 `stale_context` 或 `invalid_context`。

## 帖子访问

帖子接口贴合真实平台访问路径：

- `open-from-search`：用当前搜索上下文中的 `note_id` 打开帖子。
- `open-by-xsec`：用 `note_id`、`xsec_token` 构建 pc_share 访问链接。

两个接口都会更新当前帖子上下文，并返回帖子详情。

## 诊断信息

每个响应都会包含统一的轻量 `meta`。其中 `request_id`、`operation`、
`retry_count`、`warnings` 是固定字段；`session_id`、`diagnostics_ref` 等字段
只在适用时返回，不返回 `null` 占位。

- `request_id`
- `session_id`
- `operation`
- `retry_count`
- `warnings`
- `diagnostics_ref`

较重的诊断信息通过独立接口查询：

```text
GET /v1/sessions/{session_id}/diagnostics
```

## 错误模型

错误响应使用统一结构：

```json
{
  "ok": false,
  "error": {
    "code": "invalid_context",
    "message": "root_comment_id does not belong to current note context",
    "retryable": false,
    "action": "reopen_note",
    "details": {}
  },
  "meta": {}
}
```

`code` 是稳定业务错误码，应用层应优先根据它分支处理。`message` 只用于人类阅读，
不作为程序判断依据。`retryable` 表示是否可以不改变参数和上下文原样重试同一个
请求。`action` 是建议应用层采取的下一步动作，例如 `fix_request`、`login`、
`reopen_note`、`wait_and_retry` 或 `contact_admin`。

每个接口都会在响应区列出可能出现的 HTTP 状态码、错误码、可能原因和处理建议。

## 重试规则

接口层可以内部重试短暂性失败：

- 网络超时
- 连接重置
- HTTP 5xx

接口层不自动重试：

- 风控
- 需要登录
- 无效绑定 token
- 无效或过期上下文
- 无效 xsec token
- parser/schema 不匹配

这些错误会以稳定 `code`、`retryable` 和 `action` 返回，由应用层决定下一步。

## 公开接口与管理接口

普通应用调用 `/v1/...`。

管理端只保留强制解绑、销毁 session 等破坏性操作，放在 `/admin/v1/...`，应由
部署侧鉴权或单独网关策略保护。普通应用层不能直接调用管理接口。
