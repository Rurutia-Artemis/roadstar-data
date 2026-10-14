#!/usr/bin/env python3
"""Offline acceptance checks. Fixtures and outputs live only in TemporaryDirectory."""

import ast
import copy
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import aggregate
import validate
import validate_issue


CHECKS = 0


def check(condition, name):
    global CHECKS
    if not condition:
        raise AssertionError(name)
    CHECKS += 1


def record(identifier=1, **updates):
    item = {
        "id": f"{identifier:016x}", "week": "2026-W42", "class": "取证",
        "model": "gpt-6.1-sol", "model_version": "6.1", "effort": "high",
        "outcome": "done", "done_ratio": 1, "minutes": 10, "escalated": False,
        "quota_delta": None, "plan": "pro",
    }
    item.update(updates)
    return item


def batch(records=None):
    return {"schema": 1, "client": "roadstar", "skill_version": "1.10.0",
            "records": [record()] if records is None else records}


def body(value):
    return validate.MARKER + "\n```json\n" + json.dumps(value, ensure_ascii=False) + "\n```\n"


def issue(login, records, **updates):
    item = {"user": {"login": login}, "body": body(batch(records)),
            "labels": [{"name": "accepted"}], "state": "open"}
    item.update(updates)
    return item


def invalid(text, name):
    result = validate.validate_body(text)
    check(result["ok"] is False and 0 < len(result["errors"]) <= 10, name)
    check(set(result) == {"ok", "records", "errors"}, name + " 输出字段")


def test_validation(temp):
    good = body(batch())
    check(validate.validate_body(good) == {"ok": True, "records": 1, "errors": []}, "合格批次")
    check(validate.validate_body(good.replace("\n", "\r\n"))["ok"], "CRLF")
    check(validate.validate_body(good + "短说明")["ok"], "允许短正文")
    check(validate.validate_body(good + "字" * 200)["ok"], "正文外 200 字符边界")
    invalid(good + "字" * 201, "正文外长文本")
    invalid(good.replace(validate.MARKER, "", 1), "缺标记")
    invalid("前缀\n" + good, "标记不在第一行")
    invalid(" " + good, "标记行前空格")
    invalid(good.replace("```json", "```JSON"), "错误代码块语言")
    invalid(good.replace("```json", "```"), "无 JSON 语言标记")
    invalid(validate.MARKER + "\n{}", "缺代码块")
    invalid(good.rstrip()[:-3], "缺闭合代码块")
    invalid(good + "```json\n{}\n```", "多个 JSON 块")
    invalid(good + "```text\n隐藏内容\n```", "其他语言代码块")
    invalid(good + "~~~\n隐藏内容\n~~~", "波浪线代码块")
    invalid(validate.MARKER + "\n```json\n{坏 JSON}\n```", "坏 JSON")
    invalid(validate.MARKER + '\n```json\n{"schema":1,"schema":1}\n```', "重复键")
    invalid(good.replace('"minutes": 10', '"minutes": 10, "minutes": 10'), "记录重复键")
    invalid(good.replace('"minutes": 10', '"minutes": NaN'), "非标准 NaN")
    invalid(good.replace('"minutes": 10', '"minutes": Infinity'), "非标准 Infinity")
    invalid(good.replace("\n```\n", " {}\n```\n"), "JSON 尾随数据")
    invalid(None, "空正文")
    for value in ([], None, True, "text", 12):
        invalid(body(value), "顶层类型 " + repr(value))

    base = batch()
    for key in base:
        bad = copy.deepcopy(base)
        del bad[key]
        invalid(body(bad), "顶层必填 " + key)
    for key in record():
        bad = copy.deepcopy(base)
        del bad["records"][0][key]
        invalid(body(bad), "记录必填 " + key)
    for values in ({"schema": True}, {"schema": 2}, {"schema": "1"},
                   {"client": "other"}, {"client": []}, {"skill_version": 1},
                   {"skill_version": "1.2"}, {"skill_version": "1234.1.2"},
                   {"skill_version": "1.2.3\n"}, {"records": {}}, {"records": []},
                   {"records": [None]}, {"records": [True]}):
        bad = copy.deepcopy(base)
        bad.update(values)
        invalid(body(bad), "顶层坏值 " + repr(values))
    invalid(body(dict(base, extra="private")), "顶层额外字段")
    invalid(body(batch([dict(record(), extra="private")])), "记录额外字段")
    check(validate.validate_body(body(batch([record(i) for i in range(200)])))["ok"], "200 条边界")
    result = validate.validate_body(body(batch([record(i) for i in range(201)])))
    check(not result["ok"] and result["records"] == 201, "201 条超限")

    bad_values = {
        "id": [1, "f" * 15, "f" * 17, "F" * 16, "g" * 16, "f" * 16 + "\n"],
        "week": [202642, "2026-W00", "2026-W54", "2026-W4", "1999-W42", "2026-W42\n"],
        "class": ["其他", 1, None], "model": ["invented", 1],
        "model_version": ["6.1.0", "100", "unKnown", "6.1\n", 6.1],
        "effort": ["extreme", True], "outcome": ["success", None],
        "done_ratio": [0.15, -0.1, 1.1, True, False, "1"],
        "minutes": [-5, 1445, 12, 10.0, True, "10"],
        "escalated": [0, 1, "false", None],
        "quota_delta": ["codex_month=2", "claude_week=1000", "codex_week=2.5", "codex_week=2\n", 1, {}],
        "plan": ["enterprise", None],
    }
    for key, values in bad_values.items():
        for value in values:
            invalid(body(batch([record(**{key: value})])), f"记录坏值 {key} {value!r}")
    schema = json.loads(validate.SCHEMA_PATH.read_text(encoding="utf-8"))
    specs = schema["properties"]["records"]["items"]["properties"]
    for key, spec in specs.items():
        for value in spec.get("enum", []):
            check(validate.validate_body(body(batch([record(**{key: value})])))["ok"], f"允许枚举 {key} {value}")
    for values in ({"minutes": 0}, {"minutes": 1440}, {"quota_delta": "claude_week=-999"},
                   {"quota_delta": "codex_5h=+0"}, {"model_version": "unknown"},
                   {"model_version": "5"}, {"week": "2099-W53"}, {"escalated": True}):
        check(validate.validate_body(body(batch([record(**values)])))["ok"], "允许边界 " + repr(values))
    noisy = batch([{} for _ in range(200)])
    check(len(validate.validate_body(body(noisy))["errors"]) == 10, "最多十条错误")
    secret = "DO_NOT_ECHO_SECRET"
    errors = validate.validate_body(body(dict(base, **{secret: secret})))["errors"]
    check(secret not in json.dumps(errors), "错误不回显额外字段和值")

    def cli(args=(), text=None):
        return subprocess.run([sys.executable, str(ROOT / "scripts/validate.py"), *args],
                              input=text, text=True, capture_output=True)

    path = temp / "body.txt"
    path.write_text(good, encoding="utf-8")
    for args, text in (([str(path)], None), ([], good), (["-"], good)):
        result = cli(args, text)
        check(result.returncode == 0 and json.loads(result.stdout)["ok"], "CLI 合格文件/stdin")
    result = cli(text="bad")
    check(result.returncode == 1 and not json.loads(result.stdout)["ok"], "CLI 不合格退出码")
    check(cli(["a", "b"]).returncode == 2, "CLI 参数过多")
    check(cli([str(temp / "missing")]).returncode == 2, "CLI 文件不可读")
    path.write_bytes(b"\xff")
    check(cli([str(path)]).returncode == 2, "CLI 非 UTF-8 文件")


def test_issue_actions(temp):
    calls = []

    def fake_run(args, **kwargs):
        check(isinstance(args, list) and args[0] == "gh" and kwargs == {"check": True}, "gh 参数数组，无 shell")
        calls.append(args)

    event = {"issue": {"number": 42, "title": "dispatch-data · $(touch NEVER)", "body": body(batch())}}
    validate_issue.process_event(event, "owner/repository", run=fake_run)
    check(len(calls) == 3 and calls[0][1:4] == ["label", "create", "accepted"]
          and calls[1][1:4] == ["label", "create", "rejected"], "先保证两个标签存在")
    check("--force" in calls[0] and "--force" in calls[1], "标签存在时仍可执行")
    check(calls[2][1:8] == ["issue", "edit", "42", "--add-label", "accepted", "--remove-label", "rejected"], "合格标签")
    check(not any("$(touch" in arg for command in calls for arg in command), "标题不传 gh")
    calls.clear()
    leaked = "LEAK_PRIVATE_LOGIN_AND_BODY"
    invalid_body = body(dict(batch(), **{leaked: "`shell` $(bad)"}))
    event["issue"]["body"] = invalid_body
    validate_issue.process_event(event, "owner/repository", run=fake_run)
    expected_errors = validate.validate_body(invalid_body)["errors"]
    check(calls[2][5:8] == ["rejected", "--remove-label", "accepted"], "拒收移除旧 accepted")
    check(calls[3][1:4] == ["issue", "comment", "42"] and
          calls[3][calls[3].index("--body") + 1] == "\n".join("- " + e for e in expected_errors), "评论只列校验 errors")
    check(calls[4][1:4] == ["issue", "close", "42"], "不合格关闭 Issue")
    check(leaked not in str(calls) and "$(bad)" not in str(calls), "不向 gh 回显正文")
    calls.clear()
    event["issue"]["title"] = "normal issue"
    validate_issue.process_event(event, "owner/repository", run=fake_run)
    check(calls == [], "普通标题不处理")
    event["issue"]["title"] = "dispatch-data · data"
    event_path = temp / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event_path), "GITHUB_REPOSITORY": "owner/repository"}), \
            patch.object(validate_issue, "process_event") as process:
        validate_issue.main()
        check(process.call_args.args == (event, "owner/repository"), "从事件文件读取 body 和 title")


def test_aggregation(temp):
    fixtures = temp / "issues"
    fixtures.mkdir()
    items = []
    logins = ["PRIVATE_ALICE_7291", "PRIVATE_BOB_8324", "PRIVATE_CAROL_9132", "PRIVATE_DAVE_4518"]
    next_id = 100

    def add(login, records, **updates):
        items.append(issue(login, records, **updates))

    def rec(**values):
        nonlocal next_id
        next_id += 1
        return record(next_id, **values)

    # Advice branches: enough distinct submitters, exact sample boundaries.
    good = [rec(**{"class": "取证"}, minutes=m, escalated=(i == 0))
            for i, m in enumerate((5, 10, 15, 20, 25))]
    for login, subset in zip(logins, (good[:2], good[2:4], good[4:])):
        add(login, subset)
    # First occurrence wins, even if a later valid copy claims a different group.
    add(logins[3], [dict(good[0], **{"class": "审方案", "outcome": "stalled"})])
    for i in range(5):
        add(logins[i % 3], [rec(**{"class": "页面实现"}, outcome="done" if i < 2 else "failed")])
    for i in range(5):
        add(logins[i % 3], [rec(**{"class": "性能"}, outcome="stalled" if i < 2 else "done")])
    for i in range(5):
        add(logins[i % 3], [rec(**{"class": "复核"}, outcome="done" if i < 4 else "partial")])
    for i in range(4):
        add(logins[i % 3], [rec(**{"class": "窄回归"})])
    for i in range(6):
        add(logins[i % 2], [rec(**{"class": "补全"})])
    # Version, model and effort must each form separate groups.
    for values in ({"model_version": "5.5"}, {"model": "sonnet"}, {"effort": "low"}):
        add(logins[2], [rec(**{"class": "取证"}, **values)])
    # A single submitter's weekly cap is global, spans Issues and groups.
    capped = [rec(**{"class": "批量"}, week="2026-W43") for _ in range(55)]
    add(logins[3], capped[:30])
    add(logins[3].lower(), [capped[0]] + capped[30:])
    add(logins[0], [dict(capped[-1], **{"class": "审方案"})])
    add(logins[3], [rec(**{"class": "根因"}, week="2026-W43")])
    add(logins[3], [rec(**{"class": "批量"}, week="2026-W44")])
    add(logins[0], [rec(**{"class": "批量"}, week="2026-W43")])
    # Closed, rejected, invalid accepted, normal Issues, and PRs never contribute.
    add(logins[0], [rec(**{"class": "审方案"})], state="closed")
    add(logins[0], [rec(**{"class": "审方案"})], labels=["rejected"])
    add(logins[0], [rec(**{"class": "审方案"})], body="invalid")
    add(logins[0], [rec(**{"class": "审方案"})], title="普通 Issue")
    add(logins[0], [rec(**{"class": "审方案"})], pull_request={})
    add(logins[0], [rec(**{"class": "审方案"})], user={})
    # An invalid batch must not claim IDs and prevent a later valid occurrence.
    new = rec(**{"class": "视觉照做"})
    add(logins[0], [new, dict(rec(), minutes=7)])
    add(logins[1], [new], labels=["accepted"])
    for i, item in enumerate(items):
        (fixtures / f"{i:03d}.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")

    out = temp / "out"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/aggregate.py"), "--from-dir", str(fixtures),
                             "--output-dir", str(out)], capture_output=True, text=True)
    check(result.returncode == 0, "--from-dir 离线 CLI 成功 " + result.stderr)
    raw_json = (out / "community-table.json").read_text(encoding="utf-8")
    raw_md = (out / "community-table.md").read_text(encoding="utf-8")
    table = json.loads(raw_json)
    groups = {tuple(g[k] for k in ("class", "model", "model_version", "effort")): g for g in table["groups"]}

    def get(cls):
        return groups[(cls, "gpt-6.1-sol", "6.1", "high")]

    check(get("取证")["records"] == 5 and not any(g["class"] == "审方案" for g in table["groups"]), "去重先到先得及排除不合格 Issue")
    check(get("取证")["submitters"] == 3, "不同提交人计数，不按 Issue 数")
    check(get("批量")["records"] == 52 and get("批量")["submitters"] == 2, "同人同周跨 Issue 50 条上限及下一周重置")
    check(not any(g["class"] == "根因" for g in table["groups"]), "每周上限跨分组共享")
    check(get("取证")["done_rate"] == 1 and get("取证")["stall_rate"] == 0
          and get("取证")["escalation_rate"] == 0.2 and get("取证")["avg_minutes"] == 15, "三项比率与平均时间")
    check(get("取证")["recommendation"] == "可作起步层", "足样本可作起步层")
    check(get("页面实现")["recommendation"] == "起步层该升", "完成率低于 0.6")
    check(get("性能")["recommendation"] == "起步层该升", "卡住率高于 0.3")
    check(get("复核")["recommendation"] == "持平", "持平建议")
    check(get("窄回归")["recommendation"] == "样本不足", "不足五条记录")
    check(get("补全")["recommendation"] == "样本不足", "不足三位提交人")
    check(get("视觉照做")["records"] == 1, "重新校验整批，坏批次不占 ID")
    check(len([g for g in table["groups"] if g["class"] == "取证"]) == 4, "版本、型号、强度分别分组")
    check(table["weeks"] == {"from": "2026-W42", "to": "2026-W44"}, "统计 ISO 周范围")
    check(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", table["generated_at"]) is not None, "生成时间 UTC")
    classes = [g["class"] for g in table["groups"]]
    check(classes == sorted(classes), "按 class 排序")
    check("| 类别 | 型号 |" in raw_md and "可作起步层" in raw_md, "中文 Markdown 表格")
    for login in logins + [logins[3].lower()]:
        check(login not in raw_json + raw_md + result.stdout + result.stderr, "两种产出与日志无 login " + login)
    check(validate.MARKER not in raw_json + raw_md and '"user"' not in raw_json
          and '"body"' not in raw_json and '"id"' not in raw_json, "产出无正文或用户及逐条记录")
    check(set(table) == {"generated_at", "weeks", "groups"}, "产出顶层白名单")
    expected_fields = {"class", "model", "model_version", "effort", "records", "submitters", "done_rate",
                       "stall_rate", "escalation_rate", "avg_minutes", "recommendation"}
    check(all(set(g) == expected_fields for g in table["groups"]), "产出分组字段白名单")
    # Exact advice thresholds, including strict >0.3 and <0.6.
    for args, expected in (((5, 3, 0.9, 0), "可作起步层"), ((5, 3, 0.6, 0.3), "持平"),
                           ((5, 3, 0.59, 0), "起步层该升"), ((5, 3, 0.6, 0.31), "起步层该升"),
                           ((4, 3, 1, 0), "样本不足"), ((5, 2, 1, 0), "样本不足")):
        check(aggregate.recommendation(*args) == expected, "建议精确边界 " + repr(args))
    empty = aggregate.aggregate([])
    check(empty["groups"] == [] and empty["weeks"] == {"from": None, "to": None}, "空数据表")
    empty_dir = temp / "empty"
    empty_dir.mkdir()
    check(aggregate.main(["--from-dir", str(empty_dir), "--output-dir", str(temp / "empty-out")]) == 0, "空目录离线成功")


def test_api_pagination():
    requests = []
    first = [{"number": i} for i in range(100)]
    second = [{"number": 100}]

    def fake_open(request, timeout):
        requests.append(request)
        check(timeout == 30, "REST 请求超时")
        page = parse_qs(urlparse(request.full_url).query)["page"][0]
        return io.StringIO(json.dumps(first if page == "1" else second))

    with patch.object(aggregate, "urlopen", side_effect=fake_open):
        items = list(aggregate.fetch_issues("owner/repository", "OFFLINE_TEST_TOKEN"))
    check(len(items) == 101 and len(requests) == 2, "REST API 分页")
    for index, request in enumerate(requests, 1):
        query = parse_qs(urlparse(request.full_url).query)
        check(query == {"state": ["open"], "labels": ["accepted"], "per_page": ["100"],
                        "sort": ["created"], "direction": ["asc"], "page": [str(index)]}, "REST 查询条件")
        check(request.get_header("Authorization") == "Bearer OFFLINE_TEST_TOKEN", "REST 使用 token")
        check(request.full_url.startswith("https://api.github.com/repos/owner/repository/issues?"), "REST 固定 API 域名")
    with patch.object(aggregate, "urlopen", side_effect=AssertionError("不得联网")):
        try:
            list(aggregate.fetch_issues("owner/repository", ""))
        except ValueError:
            check(True, "无 token 不联网")
        else:
            check(False, "无 token 应失败")


def test_workflows():
    for filename in ("validate.yml", "aggregate.yml"):
        lines = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8").splitlines()
        run_indent = None
        for number, line in enumerate(lines, 1):
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if run_indent is not None and stripped and indent <= run_indent:
                run_indent = None
            # Check both inline run: and literal/folded multiline run blocks.
            match = re.match(r"^(?:-\s+)?run\s*:", stripped)
            is_run = match is not None
            if is_run:
                run_indent = indent + (2 if stripped.startswith("- ") else 0)
            if is_run or run_indent is not None:
                check("github.event.issue.body" not in line and "github.event.issue.title" not in line,
                      f"{filename}:{number} run 块无不可信 body/title 插值")
        check(not any("github.event.issue.body" in line or "github.event.issue.title" in line for line in lines),
              filename + " 完全不插值正文或标题")
    validation = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    weekly = (ROOT / ".github/workflows/aggregate.yml").read_text(encoding="utf-8")
    check("types: [opened, edited, reopened]" in validation, "Issue 事件")
    check("  issues: write\n  contents: read" in validation, "校验工作流最小权限")
    check("run: python3 scripts/validate_issue.py" in validation, "校验 Python 入口")
    check("cron: '0 15 * * 6'" in weekly and "workflow_dispatch:" in weekly, "每周日 JST 与手动触发")
    check("  contents: write\n  issues: read" in weekly, "汇总工作流最小权限")
    check("ref: main" in weekly and "git push origin HEAD:main" in weekly, "汇总提交 main")
    check("git diff --cached --quiet -- community-table.json community-table.md" in weekly, "仅有变化才提交")
    check("github-actions[bot]" in weekly and "41898282+github-actions[bot]@users.noreply.github.com" in weekly,
          "机器人提交身份")
    for path in (ROOT / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        check(True, path.name + " 语法检查")


def main():
    # A failure to intercept HTTP is itself a test failure; the suite never uses GitHub.
    with tempfile.TemporaryDirectory(prefix="roadstar-data-tests-") as directory, \
            patch("urllib.request.urlopen", side_effect=AssertionError("测试禁止网络")), \
            patch.object(aggregate, "urlopen", side_effect=AssertionError("测试禁止网络")):
        temp = Path(directory)
        test_validation(temp)
        test_issue_actions(temp)
        test_aggregation(temp)
        test_api_pagination()
        test_workflows()
    print(f"PASS {CHECKS} checks")


if __name__ == "__main__":
    main()
