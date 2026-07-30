#!/usr/bin/env python3
"""
Fetch GitCode Pull Request information.

Supports two authentication paths so the inline-review workflow works end to
end with a single OAuth2 token:

1. v5 API + ``PRIVATE-TOKEN`` (personal access token, PAT) — the historical
   path, used when ``GITCODE_TOKEN`` is available.
2. v4 API + ``Authorization: Bearer <oauth2>`` (OAuth2 access token) — the
   fallback path, used when only ``GITCODE_OAUTH_TOKEN`` is configured, or
   when the v5 API rejects the provided token with 401 (v5 does not accept
   OAuth2 Bearer tokens).

This mirrors the strategy already used by ``post_pr_comment.py`` for posting
inline comments, so a "line-level review only needs OAuth2" workflow no longer
breaks at the fetch step.

Usage:
    python fetch_pr_info.py --owner OWNER --repo REPO --pull-number NUMBER \\
        [--token TOKEN] [--output-dir DIR] [--include-comments]
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import quote

API_BASE = "https://api.gitcode.com/api/v5"
API_V4_BASE = "https://api.gitcode.com/api/v4"


class AuthError(RuntimeError):
    """Raised when the API rejects the token (HTTP 401)."""


def get_optional_pat(token: Optional[str] = None) -> Optional[str]:
    """Return a personal access token if one is available, else None.

    Never raises. Checked in order: --token arg, ``GITCODE_TOKEN`` env,
    ``git config --global gitcode.token``.
    """
    if token:
        return token

    env_token = os.environ.get("GITCODE_TOKEN")
    if env_token:
        return env_token

    try:
        result = subprocess.run(
            ["git", "config", "--global", "gitcode.token"],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return None


def get_gitcode_token(token: Optional[str] = None) -> str:
    """Get a PAT token from argument, environment, or git config.

    Kept for backward compatibility with callers that require a PAT.
    Raises ValueError if no PAT is configured.
    """
    pat = get_optional_pat(token)
    if pat:
        return pat
    raise ValueError(
        "GitCode personal access token not found. Please set it via:\n"
        "1. --token argument\n"
        "2. GITCODE_TOKEN environment variable\n"
        "3. git config --global gitcode.token <token>\n"
        "Alternatively, set GITCODE_OAUTH_TOKEN (OAuth2 access token) to use "
        "the v4 API fallback path."
    )


def get_oauth_token_optional() -> Optional[str]:
    """Return the OAuth2 access token from the environment, or None."""
    return os.environ.get("GITCODE_OAUTH_TOKEN") or None


def make_api_request(url: str, token: str) -> Any:
    """Make a v5 API request authenticated with a PAT (PRIVATE-TOKEN)."""
    headers = {
        "PRIVATE-TOKEN": token,
        "Accept": "application/json",
        "User-Agent": "gitcode-code-reviewer/1.0",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise AuthError("Authentication failed. The token was rejected (401).")
        if e.code == 404:
            raise RuntimeError(f"Resource not found: {url}")
        error_body = e.read().decode("utf-8")[:500]
        raise RuntimeError(f"API error: {e.code} - {e.reason}\n{error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")


def make_v4_request(url: str, oauth_token: str) -> Any:
    """Make a v4 API request authenticated with an OAuth2 Bearer token."""
    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "Accept": "application/json",
        "User-Agent": "gitcode-code-reviewer/1.0",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise AuthError("Authentication failed. The OAuth2 token was rejected (401).")
        if e.code == 404:
            raise RuntimeError(f"Resource not found: {url}")
        error_body = e.read().decode("utf-8")[:500]
        raise RuntimeError(f"API error: {e.code} - {e.reason}\n{error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")


# --------------------------------------------------------------------------- #
# v5 API (PAT) path
# --------------------------------------------------------------------------- #

def fetch_pr_metadata(owner: str, repo: str, pull_number: str, token: str) -> dict:
    """Fetch PR metadata using the v5 API."""
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}"
    data = make_api_request(url, token)
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault("_source", "v5")
    return data


def fetch_pr_files(owner: str, repo: str, pull_number: str, token: str) -> list:
    """Fetch PR changed files using the v5 API."""
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/files"
    return make_api_request(url, token)


def fetch_pr_diff(owner: str, repo: str, pull_number: str, token: str) -> str:
    """Fetch PR diff using the v5 API."""
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/diff"
    headers = {
        "PRIVATE-TOKEN": token,
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "gitcode-code-reviewer/1.0",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise AuthError("Authentication failed. The token was rejected (401).")
        raise RuntimeError(f"API error fetching diff: {e.code} - {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")


def fetch_pr_comments(owner: str, repo: str, pull_number: str, token: str) -> list:
    """Fetch PR comments using the v5 API."""
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
    return make_api_request(url, token)


# --------------------------------------------------------------------------- #
# v4 API (OAuth2 Bearer) fallback path
# --------------------------------------------------------------------------- #

def get_project_id(owner: str, repo: str, oauth_token: str) -> int:
    """Resolve the numeric project id via v4 GET project (OAuth2 Bearer)."""
    project_path = quote(f"{owner}/{repo}", safe="")
    url = f"{API_V4_BASE}/projects/{project_path}"
    data = make_v4_request(url, oauth_token)
    project_id = data.get("id") if isinstance(data, dict) else None
    if not project_id:
        raise RuntimeError(f"Could not resolve numeric project id for {owner}/{repo}")
    return project_id


def fetch_pr_metadata_v4(owner: str, repo: str, pull_number: str, oauth_token: str) -> dict:
    """Fetch PR metadata via v4 GET merge_request (OAuth2 Bearer).

    The v5 API does not accept OAuth2 Bearer tokens (401), so when only an
    OAuth2 token is available we use the v4 API. The response is reshaped to
    the v5 ``/pulls/{number}`` shape so downstream summary logic is unchanged.
    """
    project_id = get_project_id(owner, repo, oauth_token)
    url = f"{API_V4_BASE}/projects/{project_id}/merge_requests/{pull_number}"
    data = make_v4_request(url, oauth_token)

    diff_refs = data.get("diff_refs") or {}
    head_sha = diff_refs.get("head_sha") or data.get("sha") or ""
    base_sha = diff_refs.get("base_sha") or ""
    start_sha = diff_refs.get("start_sha") or base_sha
    author = data.get("author") or {}

    html_url = data.get("web_url") or ""
    if not html_url:
        # GitCode's v4 merge_request response omits web_url; reconstruct the
        # canonical PR URL so downstream summary links keep working.
        html_url = f"https://gitcode.com/{owner}/{repo}/pull/{pull_number}"

    return {
        "id": data.get("id"),
        "number": data.get("iid"),
        "state": data.get("state", ""),
        "title": data.get("title", ""),
        "body": data.get("description", ""),
        "html_url": html_url,
        "user": {"login": author.get("username", "")},
        "head": {"ref": data.get("source_branch", ""), "sha": head_sha},
        "base": {"ref": data.get("target_branch", ""), "sha": base_sha},
        "diff_refs": {
            "head_sha": head_sha,
            "base_sha": base_sha,
            "start_sha": start_sha,
        },
        "_source": "v4",
    }


def _count_diff_stats(diff_text: str) -> tuple[int, int]:
    """Count added/removed lines in a unified diff fragment."""
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _v4_change_status(change: dict) -> str:
    if change.get("new_file"):
        return "added"
    if change.get("deleted_file"):
        return "removed"
    if change.get("renamed_file"):
        return "renamed"
    return "modified"


def fetch_pr_files_v4(owner: str, repo: str, pull_number: str, oauth_token: str) -> list:
    """Fetch changed files (with per-file diff) via v4 /merge_requests/changes.

    GitCode's v4 ``/diffs`` and ``/repository/files`` endpoints are unavailable
    (404), but ``/merge_requests/{iid}/changes`` returns every change with its
    patch text. We map each change to the v5 ``/pulls/{number}/files`` shape
    so downstream code is agnostic to the API version.
    """
    project_id = get_project_id(owner, repo, oauth_token)
    url = (
        f"{API_V4_BASE}/projects/{project_id}"
        f"/merge_requests/{pull_number}/changes?per_page=100"
    )
    data = make_v4_request(url, oauth_token)
    changes = data.get("changes") if isinstance(data, dict) else None
    if changes is None and isinstance(data, list):
        changes = data
    changes = changes or []

    files: List[dict] = []
    for change in changes:
        diff_text = change.get("diff") or ""
        additions, deletions = _count_diff_stats(diff_text)
        new_path = change.get("new_path") or change.get("old_path") or ""
        files.append({
            "filename": new_path,
            "old_filename": change.get("old_path") or new_path,
            "status": _v4_change_status(change),
            "additions": additions,
            "deletions": deletions,
            "patch": diff_text,
        })
    return files


def build_diff_from_files(files: list) -> str:
    """Assemble a unified .patch blob from per-file v4 change diffs."""
    patches = [f.get("patch", "") for f in files if f.get("patch")]
    return "\n\n".join(patches)


def fetch_pr_comments_v4(owner: str, repo: str, pull_number: str, oauth_token: str) -> list:
    """Fetch PR comments via v4 ``/merge_requests/discussions`` (OAuth2 Bearer).

    GitCode v4 exposes discussions (GitLab-style threads) at
    ``/merge_requests/{iid}/discussions``; the flat ``/notes`` endpoint is
    unavailable (404). We flatten each discussion's ``notes`` into a single
    list in the v5 ``/pulls/{number}/comments`` shape.
    """
    project_id = get_project_id(owner, repo, oauth_token)
    url = (
        f"{API_V4_BASE}/projects/{project_id}"
        f"/merge_requests/{pull_number}/discussions?per_page=100"
    )
    data = make_v4_request(url, oauth_token)
    if isinstance(data, dict):
        discussions = data.get("data") or data.get("discussions") or []
    elif isinstance(data, list):
        discussions = data
    else:
        discussions = []

    comments = []
    for discussion in discussions:
        for note in discussion.get("notes") or []:
            author = note.get("author") or {}
            comments.append({
                "id": note.get("id"),
                "body": note.get("body", ""),
                "user": {"login": author.get("username", "")},
                "created_at": note.get("created_at", ""),
            })
    return comments


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def _resolve_credentials(args) -> tuple[Optional[str], Optional[str]]:
    """Return (pat, oauth_token). Either or both may be present."""
    return get_optional_pat(args.token), get_oauth_token_optional()


def _no_token_error() -> str:
    return (
        "No GitCode token found. Provide one of:\n"
        "  - --token <personal-access-token>\n"
        "  - GITCODE_TOKEN environment variable (personal access token)\n"
        "  - git config --global gitcode.token <token>\n"
        "  - GITCODE_OAUTH_TOKEN environment variable (OAuth2 access token, "
        "obtained from the browser; uses the v4 API fallback)\n"
        "For a line-level review workflow you only need GITCODE_OAUTH_TOKEN."
    )


def main():
    parser = argparse.ArgumentParser(description="Fetch GitCode PR information")
    parser.add_argument("--owner", required=True, help="Repository owner/namespace")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument("--pull-number", required=True, help="Pull request number")
    parser.add_argument("--token", help="GitCode personal access token (PAT)")
    parser.add_argument("--output-dir", default=".", help="Output directory for fetched data")
    parser.add_argument("--include-comments", action="store_true", help="Include existing PR comments")

    args = parser.parse_args()

    pat, oauth = _resolve_credentials(args)
    if not pat and not oauth:
        print(f"Error: {_no_token_error()}", file=sys.stderr)
        sys.exit(1)

    # A token that can be used as an OAuth2 Bearer on the v4 API. OAuth takes
    # priority; a PAT is also accepted as a last-resort Bearer so that a token
    # mistakenly placed in GITCODE_TOKEN can still recover via v4.
    v4_token = oauth or pat

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching PR #{args.pull_number} from {args.owner}/{args.repo}...")
    print()

    try:
        # ---- Resolve metadata (decides the API path for the rest) -------- #
        metadata: Optional[dict] = None
        used_v4 = False

        if pat:
            print("  Fetching PR metadata (v5 API, PAT)...")
            try:
                metadata = fetch_pr_metadata(args.owner, args.repo, args.pull_number, pat)
            except AuthError:
                if v4_token:
                    print("    v5 rejected the token (401). "
                          "Retrying via v4 API with OAuth2 Bearer...")
                    metadata = None
                else:
                    raise
            except RuntimeError as e:
                if v4_token:
                    print(f"    v5 request failed: {e}. "
                          f"Retrying via v4 API with OAuth2 Bearer...")
                    metadata = None
                else:
                    raise

        if metadata is None:
            used_v4 = True
            print("  Fetching PR metadata (v4 API, OAuth2 Bearer)...")
            metadata = fetch_pr_metadata_v4(
                args.owner, args.repo, args.pull_number, v4_token
            )

        # ---- Changed files (and diff, when on v4) ------------------------ #
        if used_v4:
            print("  Fetching changed files (v4 /merge_requests/changes)...")
            pr_files = fetch_pr_files_v4(
                args.owner, args.repo, args.pull_number, v4_token
            )
            pr_diff = build_diff_from_files(pr_files)
        else:
            print("  Fetching changed files...")
            pr_files = fetch_pr_files(
                args.owner, args.repo, args.pull_number, pat
            )
            print("  Fetching PR diff...")
            try:
                pr_diff = fetch_pr_diff(
                    args.owner, args.repo, args.pull_number, pat
                )
            except RuntimeError as e:
                print(f"    [!] Warning: Could not fetch diff - {e}")
                pr_diff = ""

        # ---- Comments (optional) ----------------------------------------- #
        pr_comments = None
        if args.include_comments:
            print("  Fetching PR comments...")
            try:
                if used_v4:
                    pr_comments = fetch_pr_comments_v4(
                        args.owner, args.repo, args.pull_number, v4_token
                    )
                else:
                    pr_comments = fetch_pr_comments(
                        args.owner, args.repo, args.pull_number, pat
                    )
            except RuntimeError as e:
                print(f"    [!] Warning: Could not fetch comments - {e}")
                pr_comments = None

        # ---- Persist ------------------------------------------------------ #
        metadata_file = output_dir / "pr_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Saved metadata to {metadata_file}")

        files_file = output_dir / "pr_files.json"
        with open(files_file, "w", encoding="utf-8") as f:
            json.dump(pr_files, f, indent=2, ensure_ascii=False)
        print(f"    [OK] Saved files to {files_file}")

        if pr_diff:
            diff_file = output_dir / "pr_diff.patch"
            with open(diff_file, "w", encoding="utf-8") as f:
                f.write(pr_diff)
            print(f"    [OK] Saved diff to {diff_file}")

        if pr_comments is not None:
            comments_file = output_dir / "pr_comments.json"
            with open(comments_file, "w", encoding="utf-8") as f:
                json.dump(pr_comments, f, indent=2, ensure_ascii=False)
            print(f"    [OK] Saved comments to {comments_file}")

        # ---- Summary ------------------------------------------------------ #
        summary = {
            "owner": args.owner,
            "repo": args.repo,
            "pull_number": args.pull_number,
            "api_source": metadata.get("_source", "v5" if not used_v4 else "v4"),
            "pr_url": metadata.get("html_url", ""),
            "title": metadata.get("title", ""),
            "author": metadata.get("user", {}).get("login", ""),
            "state": metadata.get("state", ""),
            "files_changed": len(pr_files) if pr_files else 0,
            "additions": sum(f.get("additions", 0) for f in (pr_files or [])),
            "deletions": sum(f.get("deletions", 0) for f in (pr_files or [])),
            "base_branch": metadata.get("base", {}).get("ref", ""),
            "head_branch": metadata.get("head", {}).get("ref", ""),
            "head_sha": metadata.get("head", {}).get("sha", ""),
            "base_sha": metadata.get("base", {}).get("sha", ""),
        }

        summary_file = output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print()
        print("=" * 50)
        print("PR Summary:")
        print("=" * 50)
        print(f"  Title:     {summary['title']}")
        print(f"  Author:    @{summary['author']}")
        print(f"  State:     {summary['state']}")
        print(f"  Source:    {summary['api_source']}")
        print(f"  Changes:   +{summary['additions']}/-{summary['deletions']} "
              f"in {summary['files_changed']} files")
        print(f"  Head SHA:  {summary['head_sha'][:8] if summary['head_sha'] else 'N/A'}")
        print(f"  Base SHA:  {summary['base_sha'][:8] if summary['base_sha'] else 'N/A'}")
        print()
        print(f"All data saved to: {output_dir.absolute()}")

    except AuthError as e:
        print(f"\nError: {e}", file=sys.stderr)
        print("If you are using an OAuth2 access token, set it as "
              "GITCODE_OAUTH_TOKEN (not GITCODE_TOKEN) so the v4 API fallback "
              "is used.", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
