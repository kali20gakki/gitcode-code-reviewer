# GitCode Code Reviewer

面向 Codex 的 GitCode Pull Request 审查 Skill。它会先拉取 PR 元数据、变更文件和 diff，再结合仓库上下文做更可靠的代码审查，并支持将审查结果以 GitCode 行级评论或 Review Summary 的形式发布回 PR。

## 适用场景

- 审查 GitCode PR，并输出结构化审查结论
- 基于 PR 链接自动拉取 metadata、diff 和变更文件
- 在本地仓库上下文中分析调用链、配置项和测试覆盖
- 将审查意见发布为 GitCode 行级评论或总评

## 特性

- 面向 GitCode PR 的专用审查流程，而不是只看 patch
- 内置 GitCode Token 获取与校验逻辑
- 支持抓取 PR 元数据、文件列表、diff、评论
- 支持发布逐行评论和普通 Review
- 评论格式统一为“四段式”：严重程度、问题、原因、怎么改
- 无第三方 Python 依赖，默认使用标准库即可运行

## 仓库结构

```text
.
├── SKILL.md                      # Codex Skill 主说明，定义触发条件与工作流
├── README.md                     # GitHub 开源说明文档
├── scripts/
│   ├── fetch_pr_info.py          # 拉取 GitCode PR 信息
│   ├── post_pr_comment.py        # 发布 PR 评论或 Review
│   └── setup_token.py            # 校验并配置 GitCode Token
├── examples/
│   └── sample_comments.json      # 行级评论 JSON 示例
└── references/
    └── gitcode_api.md            # GitCode API 参考说明
```

## 工作方式

1. 从 GitCode PR 链接中解析 `owner`、`repo` 和 `pull_number`
2. 通过 GitCode API 获取 PR 元数据、文件列表和 diff
3. 结合目标仓库代码上下文做“有证据”的审查
4. 先向用户展示结论，再按需发布回 GitCode PR

这个 Skill 的重点不是“只点评 diff”，而是要求结合基线实现、调用链、配置和测试来判断改动是否正确。

## 前置要求

### 运行环境

- Python 3.10+
- 可访问 GitCode API 的网络环境
- 一个具备相应权限的 GitCode Personal Access Token

### GitCode Token 权限

建议创建专用 Token，并授予以下权限：

- `pull_requests`：读取和写入
- `issues`：读取和写入
- `projects`：读取

## 安装到 Codex、OpenCode、Claude Code

推荐优先使用 [`skills`](https://github.com/vercel-labs/skills) CLI 安装。它可以把同一个 Skill 安装到多个 Agent，并自动放到对应目录中。

### 方式一：用 skills CLI 安装

先把下面的仓库地址替换成你发布后的 GitHub 仓库：

```bash
npx skills add <your-user>/<your-repo> --list
```

#### 安装到 Codex

全局安装：

```bash
npx skills add <your-user>/<your-repo> \
  --skill gitcode-code-reviewer \
  -a codex \
  -g \
  -y
```

默认会安装到：

- `~/.codex/skills/`

#### 安装到 OpenCode

全局安装：

```bash
npx skills add <your-user>/<your-repo> \
  --skill gitcode-code-reviewer \
  -a opencode \
  -g \
  -y
```

默认会安装到：

- `~/.config/opencode/skills/`

OpenCode 也支持原生技能目录：

- 项目级：`.opencode/skills/`
- 全局：`~/.config/opencode/skills/`

#### 安装到 Claude Code

全局安装：

```bash
npx skills add <your-user>/<your-repo> \
  --skill gitcode-code-reviewer \
  -a claude-code \
  -g \
  -y
```

默认会安装到：

- `~/.claude/skills/`

#### 一次安装到多个 Agent

```bash
npx skills add <your-user>/<your-repo> \
  --skill gitcode-code-reviewer \
  -a codex \
  -a opencode \
  -a claude-code \
  -g \
  -y
```

#### 项目级安装

如果你希望把 Skill 跟项目一起提交到仓库，而不是装到用户全局目录，可以去掉 `-g`。`skills` CLI 会安装到当前项目对应的 Agent 目录中。

常见项目级目录：

- Codex：`.agents/skills/`
- OpenCode：`.agents/skills/` 或 `.opencode/skills/`
- Claude Code：`.claude/skills/`

### 方式二：手动安装

如果你不想依赖 `skills` CLI，也可以直接复制或软链接到对应 Agent 的技能目录。

#### 手动安装到 Codex

```bash
mkdir -p ~/.codex/skills
ln -s "/absolute/path/to/gitcode-code-reviewer" ~/.codex/skills/gitcode-code-reviewer
```

#### 手动安装到 OpenCode

```bash
mkdir -p ~/.config/opencode/skills
ln -s "/absolute/path/to/gitcode-code-reviewer" ~/.config/opencode/skills/gitcode-code-reviewer
```

如果你希望按 OpenCode 的项目级原生目录安装，也可以这样放：

```bash
mkdir -p .opencode/skills
ln -s "/absolute/path/to/gitcode-code-reviewer" .opencode/skills/gitcode-code-reviewer
```

#### 手动安装到 Claude Code

```bash
mkdir -p ~/.claude/skills
ln -s "/absolute/path/to/gitcode-code-reviewer" ~/.claude/skills/gitcode-code-reviewer
```

### 安装后如何验证

你可以先检查仓库是否能被识别：

```bash
npx skills add <your-user>/<your-repo> --list
```

如果输出里能看到 `gitcode-code-reviewer`，说明这个 Skill 已经可以被安装。

### 作为团队共享 Skill 仓库

如果你打算把它作为 GitHub 开源 Skill 发布，推荐：

- 仓库根目录保留 `SKILL.md`
- 将脚本放在 `scripts/`
- 将参考文档放在 `references/`
- 在 README 中明确写出不同 Agent 的安装路径、Token 配置和使用示例

这样其他用户克隆后就能直接通过 `npx skills add`，或者手动复制到本地 Skill 目录中使用。

## 配置 GitCode Token

此 Skill 会按以下优先级查找 Token：

1. `--token` 命令行参数
2. 环境变量 `GITCODE_TOKEN`
3. Git 全局配置 `gitcode.token`

### 推荐方式：使用 Git 全局配置

```bash
python3 scripts/setup_token.py
```

只验证当前 Token 是否可用：

```bash
python3 scripts/setup_token.py --verify-only
```

也可以手动设置：

```bash
git config --global gitcode.token <your-token>
```

或：

```bash
export GITCODE_TOKEN=<your-token>
```

## 使用方式

### 在 Codex 中直接触发

当用户提到以下需求时，这个 Skill 适合被触发：

- `review this PR`
- `帮我检查这个 GitCode PR`
- `分析一下这个 PR 的风险`
- 直接贴一个 GitCode PR 链接，例如 `https://gitcode.com/owner/repo/pull/123`

推荐提示词示例：

```text
请 review 这个 GitCode PR，并先给我展示摘要，不要直接发评论：
https://gitcode.com/owner/repo/pull/123
```

```text
检查这个 PR 是否有回归风险，重点看兼容性、测试覆盖和调用链：
https://gitcode.com/owner/repo/pull/123
```

```text
帮我审查这个 GitCode PR，如果发现问题，请整理成可发布的逐行评论。
```

### 手动拉取 PR 信息

```bash
python3 scripts/fetch_pr_info.py \
  --owner <OWNER> \
  --repo <REPO> \
  --pull-number <NUMBER> \
  --output-dir ./tmp/pr-<NUMBER> \
  --include-comments
```

输出内容包括：

- `summary.json`
- `pr_metadata.json`
- `pr_files.json`
- `pr_diff.patch`
- `pr_comments.json`（仅当传入 `--include-comments` 时）

### 发布逐行评论

```bash
python3 scripts/post_pr_comment.py \
  --owner <OWNER> \
  --repo <REPO> \
  --pull-number <NUMBER> \
  --comments-file examples/sample_comments.json \
  --inline
```

### 发布普通 Review

```bash
python3 scripts/post_pr_comment.py \
  --owner <OWNER> \
  --repo <REPO> \
  --pull-number <NUMBER> \
  --body "已完成审查，建议补充边界条件测试。" \
  --review-event REQUEST_CHANGES
```

## 行级评论格式

`post_pr_comment.py` 支持结构化 JSON 输入。每条评论建议包含以下字段：

```json
[
  {
    "path": "src/main.py",
    "line": 42,
    "severity": "Critical",
    "problem": "描述当前问题",
    "reason": "解释为什么这是风险",
    "fix": "给出修改建议或代码示例",
    "side": "RIGHT"
  }
]
```

说明：

- `severity` 支持 `Critical`、`Improvement`、`Nitpick`
- `side` 默认为 `RIGHT`
- 删除行可使用 `LEFT`
- 脚本会自动将结构化字段渲染为统一的四段式 Markdown 评论正文

## 审查输出标准

这个 Skill 默认要求审查意见满足以下标准：

- 优先指出真实的行为风险，而不是堆积纯样式意见
- 结论必须结合仓库上下文，而不是只复述 diff
- 每条发现应包含文件路径、行号、严重程度和修改建议
- 正式发布前，先向用户展示审查摘要

## 开发与调试

查看脚本帮助：

```bash
python3 scripts/fetch_pr_info.py --help
python3 scripts/post_pr_comment.py --help
python3 scripts/setup_token.py --help
```

如果要调试 API 交互或补充行为说明，可以参考：

- `references/gitcode_api.md`
- `examples/sample_comments.json`
- `SKILL.md`

## 发布建议

如果你准备把这个仓库作为 GitHub 开源项目公开发布，建议再补充以下内容：

- `LICENSE`
- `agents/openai.yaml`，用于在支持的界面里提供更好的 Skill 展示信息
- 一个真实的仓库截图或示例审查结果

## 注意事项

- 本项目会访问 GitCode API，请勿把 Token 提交到仓库
- 行级评论依赖 PR 的 `base_sha` 和 `head_sha`，如果 PR 状态变化较大，建议重新抓取后再发布
- 当前脚本默认通过标准库访问 API，适合轻量集成和二次开发

## License

当前仓库尚未包含 `LICENSE` 文件。若要作为开源项目分发，建议补充合适的开源许可证后再正式发布。
