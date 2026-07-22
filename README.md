# Cloud Video Production Skills

面向客户后端或服务端 Agent 智能成片接入 Skill。

当前包含：

- [`cloud-video-production-client`](./cloud-video-production-client/SKILL.md)：创建异步成片任务、Poll 查询进度与结果、处理幂等重试，以及接收和验证 Webhook。

当前正式稳定版本为 [`v1.0.0`](https://github.com/gracefullliam/mp-agent-skills/releases/tag/v1.0.0)。生产接入必须固定 Release tag，不要把 `main` 当作可复现版本。

## 安装到 Codex

### 方式一：使用 npx skills（推荐）

全局安装到 Codex：

```bash
npx --yes skills add \
  https://github.com/gracefullliam/mp-agent-skills/tree/v1.0.0 \
  --skill cloud-video-production-client \
  --agent codex \
  --global \
  --yes
```

列出仓库可安装的 Skill，不写入本地：

```bash
npx --yes skills add \
  https://github.com/gracefullliam/mp-agent-skills/tree/v1.0.0 \
  --list
```

不加 `--global` 时安装到当前项目。安装后可检查结果：

```bash
npx skills list --global --agent codex
```

### 方式二：让 Codex 安装

在 Codex 中发送：

```text
请安装这个 Skill：
https://github.com/gracefullliam/mp-agent-skills/tree/v1.0.0/cloud-video-production-client
```

### 方式三：使用 Codex 内置安装器

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gracefullliam/mp-agent-skills \
  --path cloud-video-production-client \
  --ref v1.0.0
```

默认安装位置：

```text
~/.codex/skills/cloud-video-production-client
```

无论使用哪种方式，安装完成后都应新建一个 Codex 任务，使 Skill 被重新加载。

## 版本管理、更新与回滚

- `vX.Y.Z` 是不可变正式版本；已发布 tag 不移动、不覆盖。
- `snapshot-YYYY-MM-DD` 只用于审计和恢复，不作为客户稳定版本。
- `main` 是仓库维护状态；正式客户始终使用明确的 Release tag。

先检查 `npx skills` 是否记录了该安装：

```bash
npx --yes skills list --global --agent codex
```

只有列表中存在该 Skill 时，下面的命令才会更新它所记录的原安装源：

```bash
npx --yes skills update cloud-video-production-client --global --yes
```

如果返回 `No installed skills found matching`，说明当前副本不是由 `npx skills` 登记安装，或已不在它的安装记录中。此时不要继续重复 `update`；执行一次上面的固定版本 `skills add` 命令完成安装登记。

`skills update` 不会把一个固定 tag 自动切换到另一个 Release。升级或回滚时，应把安装 URL 中的 tag 明确改为目标版本后重新执行 `skills add`。例如回滚到当前稳定版仍使用：

```bash
npx --yes skills add \
  https://github.com/gracefullliam/mp-agent-skills/tree/v1.0.0 \
  --skill cloud-video-production-client \
  --agent codex \
  --global \
  --yes
```

## 使用

安装后可显式触发：

```text
使用 $cloud-video-production-client 创建云端模板视频。

创作意图：生成一条节奏明快的宠物日常短片
素材：
- asset_type: video
  asset_url: https://cdn.example.com/media/pet-001.mp4

使用 Poll 获取结果。
```

使用 Webhook 时：

```text
使用 $cloud-video-production-client 创建云端模板视频。
使用 Webhook 接收制作进度和结果，提交后不要持续 Poll。
callback_url: https://customer.example.com/webhooks/video-production
```

## 客户需要准备

- 具有 `produce` 权限的 `X-API-Key`。
- 客户服务端可访问的素材 HTTP/HTTPS URL。
- 使用 Webhook 时，提供公网 HTTPS 回调地址，并通过安全渠道取得 Webhook Secret。
- 能持久化 `outer_request_id`、`conversation_id` 和 `request_id` 的业务服务。

API Key 和 Webhook Secret 必须存放在客户服务端的环境变量或密钥管理系统中。不得写入提示词、Skill、源码仓库、浏览器代码、截图或日志。

## 公共接口边界

Skill 只使用以下公共接口：

```text
POST https://api-chn.fireflyfusion.cn/api/rest/mva/out/cloud/make
POST https://api-chn.fireflyfusion.cn/api/rest/mva/out/cloud/poll
```

创建任务时，每个素材只传：

```json
{
  "asset_type": "video",
  "asset_url": "https://cdn.example.com/media/example.mp4"
}
```

不要传 `asset_id`、模板编码、高光时间段、素材标签或其他未公开字段。最终结果使用 `video_url`。

## 调用模式

- 未配置 `callback_url`：每 3～5 秒 Poll，并在 `completed`、`failed` 或 `cancelled` 时停止。
- 已配置 `callback_url`：由 Webhook 推送进度和终态；仅在回调丢失、状态不确定或用户明确刷新时使用 Poll 对账。
- 网络超时或提交结果不确定：使用相同的 `outer_request_id` 重试，不能因为未收到响应就生成新的幂等标识。

## 事实来源

客户契约以飞书云文档《[智能成片-云端模板客户接入 Skill（v1.0）](https://fireflyfusion.feishu.cn/docx/C1vfdqFXeoAMWgxmhKfcTluJnIe)》为准。本仓库用于发布可由 Codex 安装的标准 Skill，不保存任何客户凭证。
