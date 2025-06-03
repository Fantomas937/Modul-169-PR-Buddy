"""
PR-Buddy v4 – full-context reviewer
-----------------------------------
• Sends the ENTIRE “before” and “after” file bodies to OpenAI
• Strict rubric → score ≤ 4 or heuristics ⇒ REQUEST_CHANGES
• Labels:  big-pr · needs-work · looks-good
• Includes flake8 summary
• Still chunks to 20 k chars/side to avoid model hard limit
"""

import os, re, textwrap, requests
from pathlib import Path
from github import Github
import openai

# ── CONFIG ──────────────────────────────────────────────────────────
MODEL              = "gpt-4o-mini"   # change to "gpt-4o" if accessible
TEMPERATURE        = 0.0             # deterministic, harsher
MAX_CHARS_PER_SIDE = 20_000          # hard-cap per before/after
BIG_PR_LINES       = 400             # touched-lines threshold
RUBRIC_THRESHOLD   = 4               # ≤4 ⇒ REQUEST_CHANGES
# ────────────────────────────────────────────────────────────────────

repo_full  = os.environ["GITHUB_REPOSITORY"]
pr_number  = int(os.environ["PR_NUMBER"])
gh_token   = os.environ["GITHUB_TOKEN"]
openai.api_key = os.environ["OPENAI_API_KEY"]

gh   = Github(gh_token)
repo = gh.get_repo(repo_full)
pr   = repo.get_pull(pr_number)
print(f"🔎 Full-context review for PR #{pr_number} in {repo_full}")

# ── util: ensure label exists then apply ───────────────────────────
def ensure_label(name: str, color: str = "ededed"):
    if name not in [l.name for l in pr.get_labels()]:
        try:
            repo.get_label(name)
        except Exception:
            repo.create_label(name, color)
        pr.add_to_labels(name)
        print(f"🏷️  Added label '{name}'")

# ── heuristics before LLM call ─────────────────────────────────────
touched = sum(f.changes for f in pr.get_files())
if touched > BIG_PR_LINES:
    ensure_label("big-pr", "f9d0c4")

force_request = False
for f in pr.get_files():
    if f.filename.startswith("prbuddy/") and f.deletions > f.additions:
        ensure_label("needs-work", "d93f0b")
        force_request = True
        break

# ── flake8 context ─────────────────────────────────────────────────
lint_text = Path("lint.txt").read_text()[:4000] if Path("lint.txt").exists() else "No lint output."

# ── build review body ──────────────────────────────────────────────
sections, token_total = [], 0

for file in pr.get_files():
    # skip binary deletions etc.
    if file.status == "removed" or not file.filename.endswith((".py", ".js", ".ts", ".go", ".java", ".cpp", ".c", ".rb", ".rs", ".md")):
        continue

    # full BEFORE & AFTER
    try:
        before = repo.get_contents(file.filename, ref=pr.base.sha).decoded_content.decode()
    except Exception:
        before = ""
    try:
        after = repo.get_contents(file.filename, ref=pr.head.sha).decoded_content.decode()
    except Exception:
        after = file.patch or ""

    before = before[:MAX_CHARS_PER_SIDE]
    after  = after[:MAX_CHARS_PER_SIDE]

    prompt = textwrap.dedent(f"""
    ROLE: uncompromising senior engineer.

    Compare BEFORE vs AFTER below.

    ① List critical issues (logic, style, tests, security) with line refs  
    ② Suggest concrete fixes  
    ③ Finish with ONE line:  SCORE: X/5  (1 = awful, 5 = outstanding)

    ================== BEFORE ({file.filename}) ==================
    {before}
    ================== AFTER ({file.filename}) ===================
    {after}
    =============================================================

    flake8 summary:
    {lint_text}
    """)

    resp = openai.ChatCompletion.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    token_total += resp.usage.total_tokens
    sections.append(f"### {file.filename}\n{resp.choices[0].message.content.strip()}")

if not sections:
    sections.append("_No source files to review._")

body = "\n\n---\n\n".join(sections)

# ── parse score & final decision ───────────────────────────────────
m = re.search(r"SCORE:\s*([1-5])/5", body)
score = int(m.group(1)) if m else RUBRIC_THRESHOLD
print(f"Rubric score: {score}  |  total tokens: {token_total}")

if force_request or score <= RUBRIC_THRESHOLD:
    event = "REQUEST_CHANGES"
    ensure_label("needs-work", "d93f0b")
else:
    event = "COMMENT"
    ensure_label("looks-good", "0e8a16")

pr.create_review(body=body, event=event)
print(f"✅ Posted {event} review")
