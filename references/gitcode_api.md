# GitCode API 参考

GitCode API 同时支持 GitLab v4 API 和 GitHub v5 API 格式。

## 基础信息

- **v5 API 基础 URL**: `https://api.gitcode.com/api/v5` (GitHub 兼容)
- **v4 API 基础 URL**: `https://api.gitcode.com/api/v4` (GitLab 兼容)
- **认证方式**：v5 用 `PRIVATE-TOKEN` Header（个人访问令牌，PAT）；v4 GET 还接受 `Authorization: Bearer` Header（OAuth2 访问令牌）。v5 不接受 OAuth2 Bearer（返回 401），因此仅有 OAuth2 令牌时改走 v4 GET。

## 认证

### 获取 Token

1. 登录 GitCode
2. 进入个人设置 -> 私人令牌 (Personal Access Token)
3. 生成新令牌，勾选所需权限：
   - `pull_requests` (读取和写入)
   - `issues` (读取和写入)
   - `projects` (读取)

### 使用 Token

在请求头中添加：
```
PRIVATE-TOKEN: YOUR_TOKEN
```

## v5 API (GitHub 兼容)

### PR 相关

#### 获取 PR 详情
```
GET /repos/{owner}/{repo}/pulls/{number}
```

响应示例：
```json
{
  "id": 12345,
  "number": 109,
  "state": "open",
  "title": "PR标题",
  "head": {
    "sha": "abc123...",
    "ref": "feature-branch"
  },
  "base": {
    "sha": "def456...",
    "ref": "main"
  }
}
```

#### 获取 PR 文件列表
```
GET /repos/{owner}/{repo}/pulls/{number}/files
```

#### 获取 PR Diff
```
GET /repos/{owner}/{repo}/pulls/{number}/diff
```

#### 获取 PR 评论
```
GET /repos/{owner}/{repo}/pulls/{number}/comments
```

#### 创建 PR 普通评论
```
POST /repos/{owner}/{repo}/pulls/{number}/comments
```

请求体：
```json
{
  "body": "Comment text"
}
```

#### 创建 PR Review
```
POST /repos/{owner}/{repo}/pulls/{number}/reviews
```

请求体：
```json
{
  "body": "Review summary",
  "event": "COMMENT"
}
```

`event` 可选值: `COMMENT`, `APPROVE`, `REQUEST_CHANGES`

> **注意**: 审查接口路径为 `/review`（单数），不是 `/reviews`。
> 此外，该接口要求 token 持有者对仓库具有 reviewer/approver 权限。
> 如果返回 403（无审批权限）或 404，`post_pr_comment.py` 会自动回退为通过
> `/comments` 接口发布普通评论，确保审查内容不会丢失。

## 逐行（行级）评论

### 背景

GitCode 同时维护了两套 API：

- **公开 API** (`api.gitcode.com/api/v5`)：接受 `PRIVATE-TOKEN` 个人访问令牌，
  但 **不支持创建 diff 关联的行级评论**。`/comments` 接口会忽略所有
  `path`/`line`/`side`/`position` 等字段，只创建普通 PR 评论。
- **内部 API** (`web-api.gitcode.com/issuepr/api/v1/`)：支持 GitLab 风格的
  discussions 行级评论，但 **需要 OAuth2 会话令牌**（通过浏览器登录获取），
  个人访问令牌无法用于 POST 写入操作（返回 401）。
- **v4 API** (`api.gitcode.com/api/v4`)：POST 写入操作已全面禁用（返回 403
  "当前 /api/v4 接口已禁用，请使用 /api/v5 接口"）。GET 操作部分仍可用。

### 获取 OAuth2 令牌

发布逐行评论只需要一个 OAuth2 访问令牌：

1. **`GITCODE_OAUTH_TOKEN`**（OAuth2 访问令牌）：用于所有操作
   - v4 GET merge_request：获取 PR 的 `diff_refs`（head_sha/base_sha/start_sha）
   - v4 GET project：获取数字项目 ID
   - 内部 web-api POST discussions：创建 diff 关联行级评论
   - 获取方式：
     1. 在浏览器中登录 https://gitcode.com
     2. F12 → Application → Local Storage → `https://gitcode.com`
     3. 找到 `access_token` 键，复制其值
     4. `export GITCODE_OAUTH_TOKEN="复制的值"`

> OAuth2 令牌有效期约 15 天（1296000 秒），过期后需重新获取。
> v4 GET 接口接受 OAuth2 Bearer 令牌；v5 接口不接受（返回 401），
> 因此代码使用 v4 API 获取 PR 信息和项目 ID。

### 内部 API 端点

```
POST https://web-api.gitcode.com/issuepr/api/v1/projects/{project_id}/merge_requests/{iid}/discussions
```

**请求头**:
```
Authorization: Bearer {oauth_token}
Content-Type: application/json
Origin: https://gitcode.com
Referer: https://gitcode.com/
User-Agent: Mozilla/5.0 ...
```

> `Origin`、`Referer`、`User-Agent` 等浏览器请求头是必须的，否则会被 CloudWAF 拦截（返回 418）。

**`project_id` 获取**：通过 v4 GET 接口（PAT 或 OAuth2 Bearer 均可）：
```
GET https://api.gitcode.com/api/v4/projects/{owner%2Frepo}
```
返回 JSON 中的 `id` 字段即为数字项目 ID。

**请求体**（GitLab 风格 position 对象）:
```json
{
  "body": "**严重程度：** 建议\n\n**问题：** 描述问题\n\n**原因：** 解释原因\n\n**怎么改：**\n修改建议",
  "position": {
    "position_type": "text",
    "base_sha": "PR base 分支的 commit SHA",
    "head_sha": "PR head 分支的 commit SHA",
    "start_sha": "通常与 base_sha 相同",
    "new_path": "src/main.py",
    "new_line": 42
  }
}
```

**针对删除的代码行**，使用 `old_path` 和 `old_line` 代替 `new_path`/`new_line`。

**响应**（成功时 HTTP 200）:
```json
{
  "id": "discussion_id_hash",
  "individual_note": false,
  "notes": [{
    "id": 182403312,
    "type": "DiffNote",
    "body": "评论正文",
    "diff_file": "src/main.py",
    "new_line": 42,
    "resolvable": true,
    "position": {
      "base_sha": "...",
      "head_sha": "...",
      "new_path": "src/main.py",
      "new_line": 42,
      "position_type": "text"
    }
  }]
}
```

`type: "DiffNote"` 确认评论是 diff 关联的（而非普通评论）。

### Python 示例

```python
import urllib.request
import json

PAT = "your_personal_access_token"
OAUTH_TOKEN = "your_oauth2_access_token"
WEB_API = "https://web-api.gitcode.com"
V4 = "https://api.gitcode.com/api/v4"

def get_project_id(owner, repo):
    """Get numeric project ID via v4 GET (PAT auth)."""
    from urllib.parse import quote
    encoded = quote(f"{owner}/{repo}", safe="")
    url = f"{V4}/projects/{encoded}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": PAT})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["id"]

def post_diff_inline_comment(project_id, mr_iid, path, line, body, sha_info):
    """Post a diff-attached inline comment via internal web-api."""
    url = (f"{WEB_API}/issuepr/api/v1/projects/{project_id}"
           f"/merge_requests/{mr_iid}/discussions")
    headers = {
        "Authorization": f"Bearer {OAUTH_TOKEN}",
        "Content-Type": "application/json",
        "Origin": "https://gitcode.com",
        "Referer": "https://gitcode.com/",
        "User-Agent": "Mozilla/5.0 ...",
    }
    payload = {
        "body": body,
        "position": {
            "position_type": "text",
            "base_sha": sha_info["base_sha"],
            "head_sha": sha_info["head_sha"],
            "start_sha": sha_info["start_sha"],
            "new_path": path,
            "new_line": line,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

# 使用示例
project_id = get_project_id("Ascend", "msprof")
sha_info = {
    "base_sha": "2eaeb2eb8d3d14b0b512c71a2b36da292600d63e",
    "head_sha": "68cc65b2069266c23398e67f278b5d56d0d307e0",
    "start_sha": "2eaeb2eb8d3d14b0b512c71a2b36da292600d63e",
}
result = post_diff_inline_comment(
    project_id, 388,
    "analysis/csrc/application/database/db_assembler.cpp",
    1294,
    "**严重程度：** 建议\n\n**问题：** ...",
    sha_info,
)
```

## 注意事项

1. **令牌**:
   - `GITCODE_OAUTH_TOKEN`（OAuth2）：用于逐行评论的全部操作（v4 GET + 内部 web-api POST），也用于 `fetch_pr_info.py` 在仅有 OAuth2 令牌时经 v4 回退获取 PR 信息
   - `GITCODE_TOKEN`（PAT）：`fetch_pr_info.py` 走 v5 的主路径，以及 `--body` 模式发布整体审查结论时使用
   - v5 API 不接受 OAuth2 Bearer 令牌；v4 GET 接受。`fetch_pr_info.py` 据此自动在 PAT/OAuth2 之间选择 API 路径

2. **CloudWAF**: 内部 API 需要 `Origin`/`Referer`/`User-Agent` 浏览器请求头，
   否则返回 418

3. **审查接口**:
   - 路径为 `/review`（单数），不是 `/reviews`
   - 需要仓库的 reviewer/approver 权限；权限不足时自动回退为普通评论

4. **SHA 值获取**:
   - v5 从 PR 详情接口获取 `head.sha` 和 `base.sha`；v4 从 `diff_refs` 获取 `head_sha`/`base_sha`/`start_sha`
   - `start_sha` 通常与 `base_sha` 相同

5. **v4 diff 端点**:
   - GitCode v4 的 `/merge_requests/{iid}/diffs` 与 `/repository/files` 返回 404
   - 改用 `/merge_requests/{iid}/changes` 获取每个变更文件的 patch，再拼装为完整 diff

5. **错误处理**:
   - 400 Bad Request: 参数错误或 OAuth2 令牌无效
   - 401 Unauthorized: Token 无效或权限不足
   - 403 Forbidden: v4 POST 已禁用，或审查接口权限不足
   - 418 I'm a teapot: CloudWAF 拦截（缺少浏览器请求头）
   - 404 Not Found: PR、项目或接口不存在

6. **Rate Limiting**:
   - 注意 API 调用频率限制
   - 建议在连续调用之间添加短暂延迟

## 参考链接

- GitCode API 文档: https://docs.gitcode.com/docs/apis/
- GitCode OAuth2 文档: https://docs.gitcode.com/docs/apis/oauth
- GitLab API 文档: https://docs.gitlab.com/ce/api/
- GitHub API 文档: https://docs.github.com/en/rest
