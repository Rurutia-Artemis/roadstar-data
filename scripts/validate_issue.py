#!/usr/bin/env python3
"""Actions entry point: event JSON -> validator -> gh argument arrays, never shell."""

import json
import os
from pathlib import Path
import re
import subprocess

from validate import validate_body


def process_event(event, repository, run=subprocess.run):
    issue = event.get("issue", {})
    title = issue.get("title")
    if not isinstance(title, str) or not title.startswith("dispatch-data ·"):
        return
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("仓库名称无效")
    number = issue.get("number")
    if type(number) is not int or number < 1:
        raise ValueError("Issue 编号无效")
    result = validate_body(issue.get("body"))

    def gh(*args):
        run(["gh", *args, "--repo", repository], check=True)

    for label, color, description in (
        ("accepted", "2da44e", "通过 Roadstar 数据校验"),
        ("rejected", "cf222e", "未通过 Roadstar 数据校验"),
    ):
        gh("label", "create", label, "--color", color, "--description", description, "--force")
    gh("issue", "edit", str(number), "--add-label", "accepted" if result["ok"] else "rejected",
       "--remove-label", "rejected" if result["ok"] else "accepted")
    if not result["ok"]:
        # The comment contains only the bounded validator errors, never the body.
        comment = "\n".join("- " + error for error in result["errors"])
        gh("issue", "comment", str(number), "--body", comment)
        gh("issue", "close", str(number))


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    process_event(event, os.environ["GITHUB_REPOSITORY"])


if __name__ == "__main__":
    main()
