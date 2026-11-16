import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
import requests
from dotenv import load_dotenv

REPO_DIR = Path(r"D:\Github\Govt_Exam_Scrapper")
load_dotenv(REPO_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DOC_TARGETS = [
    REPO_DIR / "docs" / "SCRAPER_CHANGELOG.md",
    Path(r"C:\Users\abhik\Desktop\Govt Exam Scrapper\docs\SCRAPER_CHANGELOG.md"),
]


def run_git(*args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(REPO_DIR), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return res.stdout.strip()


def get_context() -> tuple[str, str, list[str]]:
    status = run_git("status", "--porcelain", "src/")
    if status:
        commit_msg = "Uncommitted local changes in src/"
        diff = run_git("diff", "HEAD", "--", "src/")
        files = run_git("diff", "--name-only", "HEAD", "--", "src/").splitlines()
    else:
        commit_msg = run_git("log", "-1", "--pretty=%s")
        diff = run_git("diff", "HEAD~1", "HEAD", "--", "src/")
        files = run_git("diff", "--name-only", "HEAD~1", "HEAD", "--", "src/").splitlines()
    return commit_msg, diff[:10000], [f for f in files if f]


def generate_entry_with_groq(commit_msg: str, diff: str, files: list[str], extra_note: str) -> str | None:
    if not GROQ_API_KEY or (not diff and not extra_note):
        return None

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    try:
        m_res = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
        if m_res.status_code == 200:
            ids = [m["id"] for m in m_res.json().get("data", [])]
            preferred = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3-32b", "qwen/qwen3.6-27b"]
            for p in preferred:
                if p in ids:
                    model = p
                    break
    except Exception:
        pass

    today_str = date.today().isoformat()
    prompt = f"""You are maintaining docs/SCRAPER_CHANGELOG.md for gov-exam-scraper.
Generate ONE concise Markdown changelog entry using this exact format (no code fences, no intro text):

## {today_str} — <Portal or Feature Name> (`<domain or module>`)
- **Affected Component:** `{', '.join(files) if files else 'src/gov_exam_scraper/'}`
- **Symptom:** <What broke or what gap existed>
- **What Changed in DOM / PDF / Network:** <Exact HTML/DOM/URL/API shift, or N/A if feature upgrade>
- **Patch Applied:** <Exact selector, regex, fallback, or parser change made>
- **Interview Takeaway:** <1-sentence lesson on resilience, observability, or trade-offs>

Commit message: {commit_msg}
Optional developer note: {extra_note or 'None'}
Git diff (truncated):
{diff}
"""
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 500,
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
        print(f"Groq fallback triggered: {exc}")
    return None


def build_fallback_entry(commit_msg: str, files: list[str], extra_note: str) -> str:
    today_str = date.today().isoformat()
    comp = ", ".join(f"`{f}`" for f in files) if files else "`src/gov_exam_scraper/`"
    summary = extra_note or commit_msg or "Routine scraper/parser milestone update"
    return (
        f"## {today_str} — {summary[:70]} (`gov-exam-scraper`)\n"
        f"- **Affected Component:** {comp}\n"
        f"- **Symptom:** {summary}\n"
        f"- **What Changed in DOM / PDF / Network:** Recorded automatically from local Git state.\n"
        f"- **Patch Applied:** {commit_msg}\n"
        f"- **Interview Takeaway:** Keeping structured change logs alongside code preserves debugging context for maintenance and interviews."
    )


def prepend_entry(entry: str) -> list[Path]:
    updated_paths = []
    for target in DOC_TARGETS:
        if not target.exists():
            continue
        content = target.read_text(encoding="utf-8")
        if entry.splitlines()[0] in content:
            print(f"Already logged in: {target}")
            continue

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

        target.write_text(new_content, encoding="utf-8")
        updated_paths.append(target)
        print(f"Updated: {target}")
    return updated_paths


def main() -> None:
    commit_msg, diff, files = get_context()
    if "[skip changelog]" in commit_msg:
        return

    print(f"Inspecting: {commit_msg}")
    extra_note = ""
    if "--auto" not in sys.argv:
        try:
            extra_note = input("Optional 1-line note (or press Enter to auto-summarize git diff): ").strip()
        except EOFError:
            pass

    entry = generate_entry_with_groq(commit_msg, diff, files, extra_note)
    if not entry:
        entry = build_fallback_entry(commit_msg, files, extra_note)

    print("\n--- Generated Entry ---")
    print(entry)
    print("-----------------------\n")

    updated = prepend_entry(entry)
    if any(p == DOC_TARGETS[0] for p in updated):
        subprocess.run(["git", "-C", str(REPO_DIR), "add", "docs/SCRAPER_CHANGELOG.md"], check=False)
        subprocess.run(
            ["git", "-C", str(REPO_DIR), "commit", "-m", "docs: log milestone in SCRAPER_CHANGELOG.md [skip ci] [skip changelog]"],
            check=False,
        )
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--rebase", "origin", "main"], check=False)
        subprocess.run(["git", "-C", str(REPO_DIR), "push", "origin", "main"], check=False)
        print("Committed and pushed changelog to GitHub!")


if __name__ == "__main__":
    main()
