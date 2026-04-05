#!/usr/bin/env python3
"""
从多个来源提取最新资讯，输出为 news.json
来源优先级：
  1. cron 运行日志（每日资讯推送 job）
  2. subagent runs 日志
用法: python3 extract_news.py
"""
import json
import datetime
import os
import re
import glob

CRON_LOG = os.path.expanduser(
    "~/.openclaw/cron/runs/38d81c09-7a73-4da6-8afe-1ecb546a2eab.jsonl"
)
SUBAGENTS_DIR = os.path.expanduser("~/.openclaw/subagents/")
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news.json")

NEWS_KEYWORDS = ["AI资讯", "金融资讯", "国际局势", "🤖", "💰", "🌍"]


def is_news_content(text):
    """判断文本是否包含资讯内容"""
    if not text or len(text) < 100:
        return False
    hits = sum(1 for kw in NEWS_KEYWORDS if kw in text)
    return hits >= 3


def parse_sections(text):
    """将资讯文本按板块解析为结构化数据"""
    results = []
    section_configs = [
        ("🤖", "AI资讯"),
        ("💰", "金融资讯"),
        ("🌍", "国际局势"),
    ]
    for emoji, title in section_configs:
        start = text.find(emoji)
        if start == -1:
            continue
        next_starts = []
        for e2, t2 in section_configs:
            if e2 != emoji:
                pos = text.find(e2, start + 1)
                if pos > start:
                    next_starts.append(pos)
        end = min(next_starts) if next_starts else len(text)
        section_text = text[start:end].strip()
        items = []
        item_matches = re.findall(
            r'\d+\.\s+\*\*(.+?)\*\*\s*[-–]\s*(.+?)(?=\n\d+\.|\n\n---|\Z)',
            section_text, re.DOTALL
        )
        for t, d in item_matches:
            items.append({
                "title": t.strip(),
                "desc": re.sub(r'\s+', ' ', d.strip())
            })
        results.append({
            "emoji": emoji,
            "title": title,
            "items": items,
            "raw": section_text
        })
    return results


def read_cron_log():
    """从 cron 日志中找最新成功记录"""
    if not os.path.exists(CRON_LOG):
        return None
    with open(CRON_LOG) as f:
        lines = f.readlines()
    for line in reversed(lines):
        try:
            d = json.loads(line)
            summary = d.get('summary', '')
            if d.get('status') == 'ok' and is_news_content(summary):
                return {'ts': d.get('ts', 0), 'content': summary}
        except Exception:
            pass
    return None


def read_subagent_runs():
    """从 subagent runs 日志中找最新资讯内容（当前版本 outcome 不含完整内容，保留接口）"""
    return None


def main():
    candidates = []

    cron_result = read_cron_log()
    if cron_result:
        candidates.append(cron_result)

    subagent_result = read_subagent_runs()
    if subagent_result:
        candidates.append(subagent_result)

    if not candidates:
        print("未找到有效资讯记录")
        return

    # 选最新的
    latest = max(candidates, key=lambda x: x['ts'])

    ts = latest['ts'] / 1000 if latest['ts'] > 1e10 else latest['ts']
    dt = datetime.datetime.fromtimestamp(
        ts, tz=datetime.timezone(datetime.timedelta(hours=8))
    )
    date_str = dt.strftime('%Y-%m-%d %H:%M')

    content = latest['content']
    sections = parse_sections(content)

    result = {
        "ts": latest['ts'],
        "date": date_str,
        "content": content,
        "sections": sections
    }

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 已生成 news.json，日期: {date_str}，板块数: {len(sections)}")
    for s in sections:
        print(f"  {s['emoji']} {s['title']}: {len(s['items'])} 条")

    # 同步到 GitHub 仓库
    gh_repo = os.path.expanduser("~/.openclaw/tianci-weather")
    if os.path.isdir(os.path.join(gh_repo, ".git")):
        import subprocess
        dest = os.path.join(gh_repo, "news.json")
        import shutil
        shutil.copy2(OUTPUT, dest)
        r = subprocess.run(
            ["git", "-C", gh_repo, "add", "news.json"],
            capture_output=True, text=True
        )
        r2 = subprocess.run(
            ["git", "-C", gh_repo, "commit", "-m", f"chore: 更新每日资讯 {date_str}"],
            capture_output=True, text=True
        )
        if "nothing to commit" in r2.stdout:
            print("GitHub: 无变化，跳过推送")
        else:
            r3 = subprocess.run(
                ["git", "-C", gh_repo, "push", "origin", "main"],
                capture_output=True, text=True
            )
            if r3.returncode == 0:
                print(f"✅ 已推送到 GitHub Pages")
            else:
                print(f"⚠️ 推送失败: {r3.stderr}")
    else:
        print("⚠️ GitHub 仓库未 clone，跳过推送")


if __name__ == '__main__':
    main()
