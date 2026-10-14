#!/usr/bin/env python3
"""Build a username-free community table from accepted Issues (stdlib only)."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from validate import validate_and_parse


DEFAULT_REPOSITORY = "Rurutia-Artemis/roadstar-data"


def fetch_issues(repository, token):
    """The server's oldest-first order defines first arrival for deduplication."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("仓库名称无效")
    if not token:
        raise ValueError("缺少 GITHUB_TOKEN")
    page = 1
    while True:
        query = urlencode({"state": "open", "labels": "accepted", "per_page": 100,
                           "sort": "created", "direction": "asc", "page": page})
        request = Request(f"https://api.github.com/repos/{repository}/issues?{query}", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "roadstar-data-aggregate",
        })
        with urlopen(request, timeout=30) as response:
            items = json.load(response)
        if not isinstance(items, list):
            raise ValueError("GitHub 返回的 Issue 列表无效")
        yield from items
        if len(items) < 100:
            break
        page += 1


def local_issues(directory):
    """Offline fixture order is lexicographic filename order, then record order.

    A fixture may omit title (the required local shape has only user/body/labels/state).
    If it supplies a title, the normal dispatch-data prefix check still applies.
    """
    for path in sorted(directory.glob("*.json")):
        issue = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(issue, dict):
            raise ValueError("本地 Issue 文件必须是 JSON 对象")
        yield issue


def recommendation(records, submitters, done_rate, stall_rate):
    if records < 5 or submitters < 3:
        return "样本不足"
    if done_rate >= 0.9:
        return "可作起步层"
    if done_rate < 0.6 or stall_rate > 0.3:
        return "起步层该升"
    return "持平"


def aggregate(issues):
    seen = set()
    per_user_week = Counter()
    groups = defaultdict(list)
    weeks = set()
    for issue in issues:
        if not isinstance(issue, dict) or issue.get("state") != "open" or "pull_request" in issue:
            continue
        labels = issue.get("labels", [])
        if not isinstance(labels, list):
            continue
        names = [label.get("name") if isinstance(label, dict) else label for label in labels]
        if "accepted" not in names:
            continue
        title = issue.get("title", "dispatch-data ·")
        if not isinstance(title, str) or not title.startswith("dispatch-data ·"):
            continue
        user = issue.get("user", {})
        login = user.get("login") if isinstance(user, dict) else None
        if not isinstance(login, str) or not login:
            continue
        login = login.casefold()
        result, batch = validate_and_parse(issue.get("body"))
        if not result["ok"]:
            continue
        for record in batch["records"]:
            identifier = record["id"]
            if identifier in seen:
                continue
            seen.add(identifier)
            # Dedup precedes quota: the earliest valid occurrence owns the ID,
            # including when its submitter has already exhausted this week's cap.
            limit_key = (login, record["week"])
            if per_user_week[limit_key] >= 50:
                continue
            per_user_week[limit_key] += 1
            key = tuple(record[field] for field in ("class", "model", "model_version", "effort"))
            groups[key].append((record, login))
            weeks.add(record["week"])

    output = []
    for key, entries in sorted(groups.items()):
        records = len(entries)
        submitters = len({login for _, login in entries})
        done_rate = sum(record["outcome"] == "done" for record, _ in entries) / records
        stall_rate = sum(record["outcome"] == "stalled" for record, _ in entries) / records
        escalation_rate = sum(record["escalated"] for record, _ in entries) / records
        group = dict(zip(("class", "model", "model_version", "effort"), key))
        group.update({
            "records": records, "submitters": submitters,
            "done_rate": round(done_rate, 6), "stall_rate": round(stall_rate, 6),
            "escalation_rate": round(escalation_rate, 6),
            "avg_minutes": round(sum(record["minutes"] for record, _ in entries) / records, 2),
            "recommendation": recommendation(records, submitters, done_rate, stall_rate),
        })
        output.append(group)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "weeks": {"from": min(weeks) if weeks else None, "to": max(weeks) if weeks else None},
        "groups": output,
    }


def render_markdown(table):
    weeks = table["weeks"]
    period = f"{weeks['from']} 至 {weeks['to']}" if weeks["from"] else "暂无合格记录"
    lines = ["# 社区派活经验表", "", f"生成时间（UTC）：{table['generated_at']}",
             f"统计周范围：{period}", "",
             "完成率按 outcome=done 计算；卡住率按 outcome=stalled 计算。",
             "每位提交人每周最多计 50 条，记录 ID 全局去重。", "",
             "| 类别 | 型号 | 版本 | 强度 | 记录数 | 提交人数 | 完成率 | 卡住率 | 升级补全率 | 平均分钟 | 建议 |",
             "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for group in table["groups"]:
        cells = [group[field] for field in ("class", "model", "model_version", "effort", "records", "submitters")]
        cells += [f"{group[field]:.1%}" for field in ("done_rate", "stall_rate", "escalation_rate")]
        cells += [f"{group['avg_minutes']:.2f}", group["recommendation"]]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="汇总 accepted 的 open dispatch-data Issue")
    parser.add_argument("--from-dir", type=Path, help="离线读取目录中的 Issue JSON 文件")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd())
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY))
    args = parser.parse_args(argv)
    if args.from_dir is not None and not args.from_dir.is_dir():
        parser.error("--from-dir 必须是存在的目录")
    try:
        issues = local_issues(args.from_dir) if args.from_dir is not None else fetch_issues(
            args.repo, os.environ.get("GITHUB_TOKEN", ""))
        table = aggregate(issues)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "community-table.json").write_text(
            json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "community-table.md").write_text(render_markdown(table), encoding="utf-8")
    except (OSError, UnicodeError, ValueError, HTTPError, URLError) as error:
        # Do not print response payloads, source bodies, filenames or login data.
        print(f"汇总失败：{type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
