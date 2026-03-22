---
name: gitcode-code-reviewer
description: Automated code review for GitCode Pull Requests with line-level inline comments. Use when the user wants to review a GitCode PR, analyze code changes, or post review comments to a GitCode PR. Triggers include phrases like "review this PR", "检视这个PR", "检查PR", or when a GitCode PR URL is provided (e.g., https://gitcode.com/owner/repo/pull/123).
---

# GitCode Code Reviewer

Automatically review GitCode Pull Requests and post line-level comments.

## Prerequisites

### GitCode Access Token

This skill requires a GitCode access token to fetch PR information and post comments. The token should be configured in one of these ways:

1. **Environment variable** (Recommended): `GITCODE_TOKEN`
2. **Git config**: `git config --global gitcode.token <your-token>`

If no token is found, prompt the user to provide one.

### Getting a GitCode Token

1. Login to https://gitcode.com
2. Click avatar → Settings (设置)
3. Go to "Private Tokens" (私人令牌)
4. Generate a new token with scopes:
   - `pull_requests` (read and write)
   - `issues` (read and write)
   - `projects` (read)

## Workflow

### 1. Parse PR Information

When user provides a GitCode PR URL like `https://gitcode.com/Ascend/msprof/pull/109`:

- Extract: `owner=Ascend`, `repo=msprof`, `pull_number=109`

### 2. Fetch PR Information

Use `scripts/fetch_pr_info.py` to get PR details:

```bash
python ~/.config/agents/skills/gitcode-code-reviewer/scripts/fetch_pr_info.py \
  --owner <OWNER> --repo <REPO> --pull-number <NUMBER> \
  [--token <TOKEN>] [--output-dir <DIR>]
```

This script fetches:
- PR metadata (title, description, author, state)
- Changed files with diff content
- PR comments (optional)

### 3. Clone/Update Repository

Clone the repository to a temporary location:

```bash
export GITCODE_TOKEN="your-token"
TEMP_DIR="/tmp/gitcode-review-<REPO>-<TIMESTAMP>"
git clone --depth=50 "https://oauth2:${GITCODE_TOKEN}@gitcode.com/<OWNER>/<REPO>.git" "${TEMP_DIR}"
cd "${TEMP_DIR}"

# Fetch PR branch
git fetch origin "refs/merge-requests/<NUMBER>/head:pr-<NUMBER>-source"
git checkout "pr-<NUMBER>-source"
```

### 4. In-Depth Code Review

Analyze the code changes based on the following pillars:

- **Correctness**: Does the code achieve its stated purpose without bugs or logical errors?
- **Maintainability**: Is the code clean, well-structured, and easy to understand?
- **Readability**: Is the code well-commented and consistently formatted?
- **Efficiency**: Any obvious performance bottlenecks or resource inefficiencies?
- **Security**: Any potential security vulnerabilities or insecure coding practices?
- **Edge Cases and Error Handling**: Does the code handle edge cases and errors appropriately?
- **Testability**: Is the code adequately covered by tests?

### 5. Format Review Findings

Structure findings by severity:

- **Critical**: Bugs, security issues, or breaking changes
- **Improvements**: Suggestions for better code quality or performance
- **Nitpicks**: Formatting or minor style issues (optional)

Each finding must include:
- File path
- Line number(s)
- Severity level
- **Three-section format**:
  1. **问题** - What is the problem?
  2. **原因** - Why is this a problem?
  3. **应该怎么改** - How to fix it (with code example)

### 6. Present Review Results to User

Display findings to the user before posting:

```markdown
## Code Review Summary

**PR**: [Title](URL)  
**Author**: @author  
**Status**: [Approved / Request Changes]

### Findings

#### 🔴 Critical (N issues)
1. **File**: `path/to/file.py` (Line 42)
   - **问题**: 描述问题
   - **原因**: 解释原因
   - **应该怎么改**: 提供代码示例

#### 🟡 Improvements (N issues)
...

#### 🟢 Nitpicks (N issues)
...

### Conclusion
[Clear recommendation with reasoning]
```

### 7. Post Comments to PR (Optional)

Ask the user: "Do you want to post these findings as line-level comments to the PR?"

If yes, create a comments JSON file and use `scripts/post_pr_comment.py`:

```bash
# Create comments file
cat > /tmp/pr_comments.json << 'EOF'
[
  {
    "path": "src/main.py",
    "line": 42,
    "body": "**问题：** ...\n\n**原因：** ...\n\n**应该怎么改：** ...",
    "side": "RIGHT"
  }
]
EOF

# Post inline comments
python ~/.config/agents/skills/gitcode-code-reviewer/scripts/post_pr_comment.py \
  --owner <OWNER> --repo <REPO> --pull-number <NUMBER> \
  --comments-file /tmp/pr_comments.json \
  --inline
```

**Comment body format (three-section style):**

```markdown
**问题：** 代码中存在不规范的空格

**原因：** `node = int (node_str)` 不符合 PEP 8 规范，影响可读性

**应该怎么改：**
```python
# 修改前
node = int (node_str)

# 修改后
node = int(node_str)
```
```

### 8. Cleanup

After review, clean up the temporary repository:

```bash
rm -rf /tmp/gitcode-review-<REPO>-<TIMESTAMP>
```

## Review Tone Guidelines

- Be constructive, professional, and friendly
- Explain _why_ a change is requested
- For approvals, acknowledge the specific value of the contribution
- Use respectful language; avoid commanding tone
- Always use the **three-section format** for findings

## Scripts Reference

### fetch_pr_info.py

Fetch PR information from GitCode API.

```bash
python fetch_pr_info.py \
  --owner OWNER \
  --repo REPO \
  --pull-number NUMBER \
  [--token TOKEN] \
  [--output-dir DIR] \
  [--include-comments]
```

### post_pr_comment.py

Post comments to GitCode PR.

**Post inline (line-level) comments:**
```bash
python post_pr_comment.py \
  --owner OWNER \
  --repo REPO \
  --pull-number NUMBER \
  --comments-file COMMENTS_JSON \
  --inline
```

**Post general review:**
```bash
python post_pr_comment.py \
  --owner OWNER \
  --repo REPO \
  --pull-number NUMBER \
  --body "Review summary" \
  --review-event COMMENT|APPROVE|REQUEST_CHANGES
```

### setup_token.py

Setup and verify GitCode access token.

```bash
# Interactive setup
python setup_token.py

# Verify existing token
python setup_token.py --verify-only
```

## Reference Materials

- GitCode API documentation: See [references/gitcode_api.md](references/gitcode_api.md)
- For detailed API usage, consult the reference file when needed

## Technical Notes

### API Versions

GitCode supports both v4 (GitLab-compatible) and v5 (GitHub-compatible) APIs:

- **v5 API**: Used for PR info, files, general comments
  - Base: `https://api.gitcode.com/api/v5`
  - Auth: `PRIVATE-TOKEN` header

- **v4 API**: Used for line-level inline comments
  - Base: `https://api.gitcode.com/api/v4`
  - Auth: `PRIVATE-TOKEN` header
  - Endpoint: `POST /projects/{encoded_project}/merge_requests/{mr_iid}/discussions`

### Comments JSON Format

```json
[
  {
    "path": "relative/path/to/file.py",
    "line": 42,
    "body": "Comment text in three-section format",
    "side": "RIGHT"
  }
]
```

- `path`: File path relative to repository root
- `line`: Line number in the new file
- `body`: Comment content (Markdown supported)
- `side`: `"RIGHT"` for new code (default), `"LEFT"` for deleted code
