import json
import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

REPO_DIR = Path(r"D:\Github\Govt_Exam_Scrapper")
DESKTOP_DOCS_DIR = Path(r"C:\Users\abhik\Desktop\Govt Exam Scrapper\docs")
REPO_DOCS_DIR = REPO_DIR / "docs"
STATE_FILE = REPO_DIR / "data" / "doc_sync_state.json"

load_dotenv(REPO_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_APPLIED_DB_ID = os.getenv("NOTION_APPLIED_DB_ID", "535459a2751646f4906c7c5e03f337ef")

PS_HISTORY_PATH = Path(
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt")
)


def run_git(*args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(REPO_DIR), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return res.stdout.strip()


def bootstrap_docs_folders() -> None:
    """Ensures both repo docs/ and Desktop docs/ exist and share all baseline markdown files."""
    REPO_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    if DESKTOP_DOCS_DIR.exists():
        for src_md in DESKTOP_DOCS_DIR.glob("*.md"):
            dst_md = REPO_DOCS_DIR / src_md.name
            if not dst_md.exists():
                shutil.copy2(src_md, dst_md)
        for src_md in REPO_DOCS_DIR.glob("*.md"):
            dst_md = DESKTOP_DOCS_DIR / src_md.name
            if not dst_md.exists():
                shutil.copy2(src_md, dst_md)


def get_ps_history_lines() -> list[str]:
    if not PS_HISTORY_PATH.exists():
        return []
    try:
        return PS_HISTORY_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []


def get_relevant_clipboard() -> str:
    try:
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get().strip()
        root.destroy()
    except Exception:
        return ""

    if not text or len(text) < 20:
        return ""
    keywords = (
        "gov-exam-scraper", "notion", "admit card", "rrb", "ibps", "kea", "kpsc",
        "sbi", "upsc", "cen ", "aggregators.py", "scraper.py", "track_applied.py",
        "exam name:", "application no", "milestone", "changelog", "github actions"
    )
    lower = text.lower()
    if any(k in lower for k in keywords):
        return text[:4000]
    return ""


def fetch_notion_applied_snapshot() -> dict[str, dict]:
    """Fetches all rows from NOTION_APPLIED_DB_ID with full cursor pagination."""
    if not NOTION_API_KEY or not NOTION_APPLIED_DB_ID:
        return {}

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1/databases/{NOTION_APPLIED_DB_ID}/query"
    snapshot: dict[str, dict] = {}
    has_more = True
    start_cursor = None

    while has_more:
        body: dict = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        try:
            res = requests.post(url, headers=headers, json=body, timeout=15)
            if res.status_code != 200:
                break
            data = res.json()
            for row in data.get("results", []):
                pid = row["id"]
                props = row.get("properties", {})

                def read_text(prop_name: str) -> str:
                    p = props.get(prop_name, {})
                    ptype = p.get("type")
                    if ptype == "title":
                        return "".join(t.get("plain_text", "") for t in p.get("title", []))
                    if ptype == "rich_text":
                        return "".join(t.get("plain_text", "") for t in p.get("rich_text", []))
                    if ptype == "select" and p.get("select"):
                        return p["select"].get("name", "")
                    if ptype == "url":
                        return p.get("url") or ""
                    if ptype == "date" and p.get("date"):
                        return p["date"].get("start", "")
                    return ""

                snapshot[pid] = {
                    "exam_name": read_text("Exam Name"),
                    "authority": read_text("Authority"),
                    "notif_no": read_text("Notification No"),
                    "reg_no": read_text("Registration No"),
                    "status": read_text("Status"),
                    "timeline": read_text("Exam Timeline"),
                    "notice_url": read_text("Notice Board URL"),
                    "admit_url": read_text("Admit Card URL"),
                    "latest_news": read_text("Latest News"),
                }
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
        except Exception:
            break

    return snapshot


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def collect_delta(state: dict) -> dict:
    """Collects everything changed across Git, Notion, PowerShell/Chat, and CI since last .bat run."""
    last_commit = state.get("last_git_commit", "")
    last_ps_line = state.get("last_ps_history_line", 0)
    prev_notion = state.get("notion_applied_snapshot", {})
    last_ts = state.get("last_run_timestamp", "initial baseline")

    commits: list[str] = []
    if last_commit:
        raw_log = run_git("log", f"{last_commit}..HEAD", "--pretty=format:%h | %ad | %s", "--date=short")
        for line in raw_log.splitlines():
            if "[skip changelog]" not in line and "chore(ci): update sent alerts" not in line:
                commits.append(line)
        diff_stat = run_git("diff", "--stat", f"{last_commit}..HEAD", "--", ".", ":!docs", ":!data")
        code_diff = run_git("diff", f"{last_commit}..HEAD", "--", ".", ":!docs", ":!data")
    else:
        diff_stat = ""
        code_diff = ""

    uncommitted_status = run_git("status", "--porcelain", "--", ".", ":!docs", ":!data")
    uncommitted_diff = run_git("diff", "HEAD", "--", ".", ":!docs", ":!data") if uncommitted_status else ""

    curr_notion = fetch_notion_applied_snapshot()
    notion_added: list[dict] = []
    notion_updated: list[dict] = []

    if curr_notion:
        for pid, info in curr_notion.items():
            if pid not in prev_notion:
                notion_added.append(info)
            else:
                old = prev_notion[pid]
                changed_fields = []
                for field in ("status", "timeline", "latest_news", "admit_url", "reg_no", "exam_name"):
                    if info.get(field) != old.get(field) and info.get(field):
                        changed_fields.append(f"{field}: '{old.get(field)}' -> '{info.get(field)}'")
                if changed_fields:
                    notion_updated.append({"exam_name": info["exam_name"], "changes": changed_fields})

    ps_lines = get_ps_history_lines()
    new_ps_cmds: list[str] = []
    if len(ps_lines) > last_ps_line:
        for cmd in ps_lines[last_ps_line:]:
            c = cmd.strip()
            if not c or "Log_Scraper_Milestone.bat" in c or "sync_all_docs.py" in c or "SCRAPER_CHANGELOG.md" in c:
                continue
            if any(secret in c.upper() for secret in ("API_KEY=", "BOT_TOKEN=", "WEBHOOK_URL=", "PASSWORD")):
                continue
            new_ps_cmds.append(c)

    clipboard_context = get_relevant_clipboard()
    session_notes_file = REPO_DOCS_DIR / "SESSION_NOTES.md"
    manual_notes = session_notes_file.read_text(encoding="utf-8").strip() if session_notes_file.exists() else ""

    return {
        "since": last_ts,
        "commits": commits,
        "diff_stat": diff_stat,
        "code_diff": (code_diff + "\n" + uncommitted_diff).strip()[:12000],
        "uncommitted_status": uncommitted_status,
        "notion_added": notion_added,
        "notion_updated": notion_updated,
        "curr_notion": curr_notion,
        "new_ps_cmds": new_ps_cmds[-40:],
        "total_ps_lines": len(ps_lines),
        "clipboard_context": clipboard_context,
        "manual_notes": manual_notes,
    }


def has_meaningful_changes(delta: dict) -> bool:
    return bool(
        delta["commits"]
        or delta["uncommitted_status"]
        or delta["notion_added"]
        or delta["notion_updated"]
        or delta["manual_notes"]
        or delta["clipboard_context"]
        or any(
            k in " ".join(delta["new_ps_cmds"]).lower()
            for k in ("git commit", "git push", "aggregators.py", "scraper.py", "track_applied.py", "notion", "daily-run.yml")
        )
    )


def generate_changelog_entry(delta: dict) -> str:
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M IST")

    context_lines = [f"Window: Since {delta['since']} up to {now_local}"]
    if delta["commits"]:
        context_lines.append("Git Commits:\n" + "\n".join(f"  - {c}" for c in delta["commits"]))
    if delta["diff_stat"]:
        context_lines.append("Git Diff Summary:\n" + delta["diff_stat"])
    if delta["uncommitted_status"]:
        context_lines.append("Uncommitted Files:\n" + delta["uncommitted_status"])
    if delta["notion_added"]:
        added_str = "\n".join(
            f"  - NEW EXAM: {e['exam_name']} | Auth: {e['authority']} | Advt: {e['notif_no']} | Reg: {e['reg_no']} | Status: {e['status']} | Timeline: {e['timeline']}"
            for e in delta["notion_added"]
        )
        context_lines.append("Notion Applied Exams Added:\n" + added_str)
    if delta["notion_updated"]:
        upd_str = "\n".join(
            f"  - UPDATED EXAM: {u['exam_name']} ({'; '.join(u['changes'])})"
            for u in delta["notion_updated"]
        )
        context_lines.append("Notion Applied Exams Updated:\n" + upd_str)
    if delta["new_ps_cmds"]:
        context_lines.append("Local Terminal / Chat Script Actions:\n" + "\n".join(f"  - {c[:140]}" for c in delta["new_ps_cmds"][:15]))
    if delta["manual_notes"]:
        context_lines.append("Session Notes:\n" + delta["manual_notes"][:3000])
    if delta["clipboard_context"]:
        context_lines.append("Chat / Clipboard Recap:\n" + delta["clipboard_context"][:3000])

    factual_summary = "\n\n".join(context_lines)

    if GROQ_API_KEY:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        try:
            m_res = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
            if m_res.status_code == 200:
                ids = [m["id"] for m in m_res.json().get("data", [])]
                for cand in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3-32b", "qwen/qwen3.6-27b"]:
                    if cand in ids:
                        model = cand
                        break
        except Exception:
            pass

        prompt = f"""You are maintaining docs/SCRAPER_CHANGELOG.md for gov-exam-scraper.
Summarize ALL work done since the last sync into ONE clean, chronological Markdown entry using this exact 5-bullet format (no code fences, no intro text, never include any passwords or API keys):

## {now_local} — <Concise Title Covering All Changes> (`GitHub / Notion / Scraper`)
- **Affected Component:** `<comma-separated files, Notion DBs, or workflows touched>`
- **Symptom:** <Why this work was done — e.g., new exam(s) applied, portal DOM fix, Notion status update, workflow improvement>
- **What Changed in DOM / PDF / Network:** <Exact Notion additions/updates, DOM/selector/RSS shifts, or GitHub workflow changes>
- **Patch Applied:** <Exact code/script/Notion/Git operations executed>
- **Interview Takeaway:** <1-sentence engineering lesson on automation, resilience, or observability>

Factual Delta Log:
{factual_summary}

Code Diff (if any):
{delta['code_diff'][:6000]}
"""
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 650,
                },
                timeout=20,
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"].strip()
                text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
                text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text).strip()
                if text.startswith("## "):
                    return text
        except Exception as exc:
            print(f"Groq summary fallback: {exc}")

    parts_title = []
    if delta["notion_added"]:
        parts_title.append(f"Added {len(delta['notion_added'])} Exam(s) to Notion")
    if delta["notion_updated"]:
        parts_title.append(f"Updated {len(delta['notion_updated'])} Notion Exam(s)")
    if delta["commits"]:
        parts_title.append(f"{len(delta['commits'])} Git Commit(s)")
    if not parts_title:
        parts_title.append("Session & Workspace Sync")

    title = " & ".join(parts_title)
    details = []
    for e in delta["notion_added"]:
        details.append(f"Added `{e['exam_name']}` ({e['notif_no']}, {e['reg_no']}, Status: {e['status']})")
    for u in delta["notion_updated"]:
        details.append(f"Updated `{u['exam_name']}` ({', '.join(u['changes'])})")
    for c in delta["commits"]:
        details.append(f"Commit `{c}`")
    if delta["manual_notes"]:
        details.append(f"Notes: {delta['manual_notes'][:200]}")

    return (
        f"## {now_local} — {title} (`gov-exam-scraper`)\n"
        f"- **Affected Component:** `Notion Applied DB`, `GitHub main`, `src/gov_exam_scraper/`\n"
        f"- **Symptom:** Incremental delta recorded since `{delta['since']}`.\n"
        f"- **What Changed in DOM / PDF / Network:** {'; '.join(details) if details else 'Workspace/chat milestone captured.'}\n"
        f"- **Patch Applied:** Synced Notion state, Git commits, and local session actions automatically.\n"
        f"- **Interview Takeaway:** Stateful watermark-based documentation captures incremental changes across code, databases, and workflows in a single click."
    )


def update_architecture_exam_list(curr_notion: dict[str, dict], notion_added: list[dict]) -> bool:
    """Updates tracked exam count & Tier B list in 01_SYSTEM_ARCHITECTURE_AND_PIPELINE.md when new exams are added."""
    if not notion_added or not curr_notion:
        return False

    arch_file = REPO_DOCS_DIR / "01_SYSTEM_ARCHITECTURE_AND_PIPELINE.md"
    if not arch_file.exists():
        return False

    content = arch_file.read_text(encoding="utf-8")
    total_count = len(curr_notion)
    updated = re.sub(
        r"(#### Tier B: Personal Lifecycle Tracking \()\d+(\s+Applied Exams)",
        rf"\g<1>{total_count}\g<2>",
        content,
    )

    new_bullets = []
    for idx, exam in enumerate(notion_added, start=total_count - len(notion_added) + 1):
        name = exam.get("exam_name", "New Exam")
        if name.lower() not in updated.lower():
            meta = ", ".join(x for x in [exam.get("notif_no"), exam.get("reg_no")] if x)
            suffix = f" (`{meta}`)" if meta else ""
            new_bullets.append(f"{idx}. {name}{suffix}")

    if new_bullets:
        marker = "\n---\n\n## 2. End-to-End Data Pipeline"
        if marker in updated:
            updated = updated.replace(marker, "\n" + "\n".join(new_bullets) + "\n" + marker, 1)

    if updated != content:
        arch_file.write_text(updated, encoding="utf-8")
        return True
    return False


def sync_docs_to_both_folders(entry: str, arch_updated: bool) -> None:
    bootstrap_docs_folders()
    for docs_dir in (REPO_DOCS_DIR, DESKTOP_DOCS_DIR):
        if not docs_dir.exists():
            continue
        changelog = docs_dir / "SCRAPER_CHANGELOG.md"
        if not changelog.exists():
            changelog.write_text("# Scraper & Parser Changelog (`gov-exam-scraper`)\n\n---\n\n" + entry.strip() + "\n", encoding="utf-8")
            continue

        content = changelog.read_text(encoding="utf-8")
        parts = content.split("\n---\n", 2)
        if len(parts) == 3:
            new_content = (
                parts[0]
                + "\n---\n"
                + parts[1]
                + "\n---\n\n"
                + entry.strip()
                + "\n\n---\n"
                + parts[2].lstrip("\n")
            )
        else:
            new_content = content.rstrip() + "\n\n---\n\n" + entry.strip() + "\n"
        changelog.write_text(new_content, encoding="utf-8")

    if arch_updated and DESKTOP_DOCS_DIR.exists():
        src_arch = REPO_DOCS_DIR / "01_SYSTEM_ARCHITECTURE_AND_PIPELINE.md"
        dst_arch = DESKTOP_DOCS_DIR / "01_SYSTEM_ARCHITECTURE_AND_PIPELINE.md"
        if src_arch.exists():
            shutil.copy2(src_arch, dst_arch)


def main() -> None:
    bootstrap_docs_folders()
    state = load_state()

    if "--init-baseline" in sys.argv:
        head_sha = run_git("rev-parse", "HEAD")
        ps_lines = get_ps_history_lines()
        notion_snap = fetch_notion_applied_snapshot()
        save_state(
            {
                "last_run_timestamp": datetime.now(timezone.utc).isoformat(),
                "last_git_commit": head_sha,
                "last_ps_history_line": len(ps_lines),
                "notion_applied_snapshot": notion_snap,
            }
        )
        print(
            f"Baseline watermark saved! HEAD={head_sha[:8]}, "
            f"Notion exams={len(notion_snap)}, PS history lines={len(ps_lines)}"
        )
        return

    print("Scanning incremental delta since last .bat run (Git, Notion, Terminal/Chat)...")
    delta = collect_delta(state)

    if not has_meaningful_changes(delta):
        print("Everything is already documented up to date! Zero new changes since last run.")
        return

    entry = generate_changelog_entry(delta)
    print("\n--- New Chronological Log Entry ---")
    print(entry)
    print("-----------------------------------\n")

    arch_updated = update_architecture_exam_list(delta["curr_notion"], delta["notion_added"])
    sync_docs_to_both_folders(entry, arch_updated)

    session_notes_file = REPO_DOCS_DIR / "SESSION_NOTES.md"
    if session_notes_file.exists() and delta["manual_notes"]:
        session_notes_file.unlink()

    head_sha = run_git("rev-parse", "HEAD")
    save_state(
        {
            "last_run_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_git_commit": head_sha,
            "last_ps_history_line": delta["total_ps_lines"],
            "notion_applied_snapshot": delta["curr_notion"] or state.get("notion_applied_snapshot", {}),
        }
    )

    subprocess.run(["git", "-C", str(REPO_DIR), "add", "docs/", "data/doc_sync_state.json"], check=False)
    subprocess.run(
        ["git", "-C", str(REPO_DIR), "commit", "-m", "docs: auto-sync incremental milestone log [skip ci] [skip changelog]"],
        check=False,
    )
    subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--rebase", "origin", "main"], check=False)
    subprocess.run(["git", "-C", str(REPO_DIR), "push", "origin", "main"], check=False)
    print("All docs synced & pushed to GitHub!")


if __name__ == "__main__":
    main()
