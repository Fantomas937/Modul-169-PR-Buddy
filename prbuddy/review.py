"""
PR-Buddy v5  – full-context, strict reviewer
"""

import os, re, textwrap
from pathlib import Path
from github import Github
import openai, json, sys

# ─── CONFIG ─────────────────────────────────────────────────────────
MODEL              = "gpt-4.1"
TEMPERATURE        = 0.0
MAX_CHARS_PER_SIDE = 20_000
BIG_PR_LINES       = 400
RUBRIC_THRESHOLD   = 4          # ≤4 ⇒ Request-Changes
# ────────────────────────────────────────────────────────────────────

repo_full  = os.environ["GITHUB_REPOSITORY"]
pr_number  = int(os.environ["PR_NUMBER"])
gh_token   = os.environ["GITHUB_TOKEN"]
openai.api_key = os.environ["OPENAI_API_KEY"]

gh   = Github(gh_token)
repo = gh.get_repo(repo_full)
pr   = repo.get_pull(pr_number)
print(f"🔍 Reviewing PR #{pr_number} in {repo_full}")

# — util ------------------------------------------------------------
def ensure_label(name: str, color="ededed"):
    labels = [l.name for l in pr.get_labels()]
    if name not in labels:
        try:
            repo.get_label(name)
        except Exception:
            repo.create_label(name, color)
        pr.add_to_labels(name)
        print(f"🏷️  label '{name}' added")
    # refresh cache so sidebar updates quickly
    pr.get_labels().totalCount

# — heuristics before LLM ------------------------------------------
touched = sum(f.changes for f in pr.get_files())
if touched > BIG_PR_LINES:
    ensure_label("big-pr", "f9d0c4")

force_request = False
for f in pr.get_files():
    if f.filename.startswith("prbuddy/") and f.deletions > f.additions:
        ensure_label("needs-work", "d93f0b")
        force_request = True

# — flake8 summary --------------------------------------------------
lint_text = (Path("lint.txt").read_text()[:4000]
             if Path("lint.txt").exists()
             else "No lint output.")

# — build review ----------------------------------------------------
sections, tok_total = [], 0
for f in pr.get_files():
    if f.status == "removed":          # skip deletions
        continue
    try:
        before = repo.get_contents(f.filename, ref=pr.base.sha).decoded_content.decode()
    except Exception:
        before = ""
    try:
        after = repo.get_contents(f.filename, ref=pr.head.sha).decoded_content.decode()
    except Exception:
        after = f.patch or ""

    before, after = before[:MAX_CHARS_PER_SIDE], after[:MAX_CHARS_PER_SIDE]

    prompt = textwrap.dedent(f"""
    ROLE: senior staff engineer.

    TASK:
      * Review the AFTER version against BEFORE.
      * Bullet critical issues & fixes.
      * Finish with ONE line:  SCORE: X/5

    ================= BEFORE ({f.filename}) ================
    {before}
    ================= AFTER ({f.filename}) =================
    {after}
    ========================================================

    flake8 summary (ignore if not relevant):
    {lint_text}
    """)

    resp = openai.ChatCompletion.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    tok_total += resp.usage.total_tokens
    sections.append(f"### {f.filename}\n{resp.choices[0].message.content.strip()}")

if not sections:
    sections.append("_No source to review._")

body = "\n\n---\n\n".join(sections)

# — extract score (robust) -----------------------------------------
score_match = re.search(r"score[^0-9]*([1-5])\/5", body, flags=re.I)
score = int(score_match.group(1)) if score_match else 1
if not score_match:
    body = ("⚠️ **The AI reply missed the mandatory `SCORE: X/5` line. "
            "PR-Buddy defaults to 1/5 and requests changes.**\n\n") + body
print(f"SCORE {score}/5  |  total tokens {tok_total}")

# — decide review event & labels -----------------------------------
if force_request or score <= RUBRIC_THRESHOLD:
    event = "REQUEST_CHANGES"
    ensure_label("needs-work", "d93f0b")
else:
    event = "COMMENT"
    ensure_label("looks-good", "0e8a16")

pr.create_review(body=body, event=event)
print(f"✅ Posted {event}")

# — expose summary for job-summary step ----------------------------
summary = {
    "score": f"{score}/5",
    "event": event,
    "tokens": tok_total
}
print(f"::set-output name=summary::{json.dumps(summary)}")
