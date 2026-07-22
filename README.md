# Cloud Video Production Skills

面向客户后端、可信本地 Agent 或其他服务端运行时的智能成片接入 Skill。

当前包含：

- [`cloud-video-production-client`](./cloud-video-production-client/SKILL.md)：上传用户明确选择的本地图片或视频、使用已有素材 URL 创建异步成片任务、查询进度与结果、处理幂等重试，以及接收和验证 Webhook。

## 安装到 Codex

### 方式一：使用 npx skills（推荐）

全局安装到 Codex：

```bash
npx --yes skills add gracefullliam/mp-agent-skills \
  --skill cloud-video-production-client \
  --agent codex \
  --global \
  --yes
```

也可以使用完整 GitHub URL：

```bash
npx skills add https://github.com/gracefullliam/mp-agent-skills
```

不加 `--global` 时安装到当前项目。安装后可检查结果：

```bash
npx skills list --global --agent codex
```

### 方式二：让 Codex 安装

在 Codex 中发送：

```text
请安装这个 Skill：
https://github.com/gracefullliam/mp-agent-skills/tree/main/cloud-video-production-client
```

### 方式三：使用 Codex 内置安装器

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gracefullliam/mp-agent-skills \
  --path cloud-video-production-client
```

默认安装位置：

```text
~/.codex/skills/cloud-video-production-client
```

无论使用哪种方式，安装完成后都应新建一个 Codex 任务，使 Skill 被重新加载。

## 更新已有安装

如果之前通过 `npx skills` 全局安装，使用以下命令更新到 GitHub 最新版本：

```bash
npx --yes skills update cloud-video-production-client --global --yes
```

更新子命令直接接 Skill 名称，不使用 `--skill` 或 `--agent`。如果安装在当前项目而不是全局，将 `--global` 改为 `--project`。

如果之前通过 Codex 内置安装器安装，需要先把旧目录移动为备份，因为内置安装器不会覆盖已存在的目录：

```bash
mkdir -p ~/.codex/skill-backups

mv ~/.codex/skills/cloud-video-production-client \
  ~/.codex/skill-backups/cloud-video-production-client.backup

python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo gracefullliam/mp-agent-skills \
  --path cloud-video-production-client
```

不要把备份保留在 `~/.codex/skills` 中，否则 Codex 仍可能把它识别为一个同名 Skill。确认新版可用后再自行处理备份目录。安装或更新完成后，请新建一个 Codex 任务，使 Skill 被重新加载。

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

使用本地文件时：

```text
使用 $cloud-video-production-client，把我明确指定的本地视频上传后制作云端模板视频。

本地文件：/workspace/media/pet.mp4
创作意图：生成一条节奏明快的宠物日常短片
使用 Poll 获取结果。
```

运行 Codex 或其他 Agent 的可信环境必须能读取该文件。Skill 会先调用 `/upload` 取得 URL，再调用 `/make`，不会把文件二进制或 Base64 放入提示词。

## 客户需要准备

- 具有 `produce` 权限的生产 `X-API-Key`，通过 `FIREFLY_MVA_PROD_API_KEY` 注入调用进程。
- 客户服务端可访问的素材 HTTP/HTTPS URL，或可信运行时能够读取且由用户明确选择的本地图片/视频。
- 使用 Webhook 时，提供公网 HTTPS 回调地址，并通过安全渠道取得 Webhook Secret。
- 能持久化 `outer_request_id`、`conversation_id` 和 `request_id` 的业务服务。

生产 API Key 只从 `FIREFLY_MVA_PROD_API_KEY` 读取，不得回退到 `FIREFLY_MVA_QA_API_KEY`、`API_KEY`、`X_API_KEY` 或其他环境凭据。API Key 和 Webhook Secret 必须存放在客户服务端的环境变量或密钥管理系统中，不得写入提示词、Skill、源码仓库、浏览器代码、截图或日志。

本机或部署环境配置示例：

```bash
export FIREFLY_MVA_PROD_API_KEY='<production-produce-key>'
```

真实值只在本机、CI/CD 或密钥管理器中配置，不要提交到 Git。仓库提供的 `.env.example` 只用于声明变量名。

## 公共接口边界

Skill 只使用环境 `base_url` 下的以下公共接口：

```text
POST /api/rest/mva/out/cloud/upload
POST /api/rest/mva/out/cloud/make
POST /api/rest/mva/out/cloud/poll
POST /api/rest/mva/out/cloud/queryResult
```

本地素材通过 multipart 的重复字段 `files` 上传。只有当每个返回项都有非空 `url` 时，才可映射为 `/make` 的素材：

```json
{
  "asset_id": "asset-video-001",
  "asset_type": "video",
  "asset_url": "https://cdn.example.com/media/example.mp4",
  "content_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

不要传模板编码、高光时间段、客户端模板匹配结果或其他未公开字段。Poll 的最终结果使用 `video_url`；需要海报或完整最终素材时调用 `queryResult`。

## 调用模式

- 未配置 `callback_url`：每 3～5 秒 Poll，并在 `completed`、`failed` 或 `cancelled` 时停止。
- 已配置 `callback_url`：由 Webhook 推送进度和终态；仅在回调丢失、状态不确定或用户明确刷新时使用 Poll 对账。
- 本地文件：先调用 `/upload`，任一文件上传失败时停止，不得继续调用 `/make`。
- 网络超时或提交结果不确定：使用相同的 `outer_request_id` 重试，不能因为未收到响应就生成新的幂等标识。
- `/upload` 不具备业务幂等语义；上传响应不确定时，重试可能留下未被使用的存储对象。

## 事实来源

客户契约以飞书云文档《[智能成片-云端模板客户接入 Skill（v1.0）](https://fireflyfusion.feishu.cn/docx/C1vfdqFXeoAMWgxmhKfcTluJnIe)》为准。本仓库用于发布可由 Codex 安装的标准 Skill，不保存任何客户凭证。
