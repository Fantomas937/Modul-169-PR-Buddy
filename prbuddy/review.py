"""
PR-Buddy v6  – strict, full-context reviewer
Outputs ten concise bullets (✓ good / ✗ bad) and FINAL SCORE: X/5
"""

import os, re, textwrap, json
from pathlib import Path
from github import Github
import openai

# ─── CONFIG ─────────────────────────────────────────────────────────
MODEL              = "gpt-4o"      # swap to gpt-4.1 when available
TEMPERATURE        = 0.0
MAX_CHARS_PER_SIDE = 20_000
BIG_PR_LINES       = 400
FAIL_THRESHOLD     = 4             # ≤4 ⇒ Request-Changes
# ────────────────────────────────────────────────────────────────────

repo_full  = os.environ["GITHUB_REPOSITORY"]
pr_number  = int(os.environ["PR_NUMBER"])
gh_token   = os.environ["GITHUB_TOKEN"]
openai.api_key = os.environ["OPENAI_API_KEY"]

gh   = Github(gh_token)
repo = gh.get_repo(repo_full)
pr   = repo.get_pull(pr_number)
print(f"🔎 Reviewing PR #{pr_number} in {repo_full}")

def ensure_label(name, color="ededed"):
    if name not in [l.name for l in pr.get_labels()]:
        try:
            repo.get_label(name)
        except Exception:
            repo.create_label(name, color)
        pr.add_to_labels(name)

# size label
if sum(f.changes for f in pr.get_files()) > BIG_PR_LINES:
    ensure_label("big-pr", "f9d0c4")

force_request = False
for f in pr.get_files():
    if f.filename.startswith("prbuddy/") and f.deletions > f.additions:
        ensure_label("needs-work", "d93f0b")
        force_request = True
        break

lint_text = Path("lint.txt").read_text()[:4000] if Path("lint.txt").exists() else "No lint output."

sections, tot_tokens = [], 0
for f in pr.get_files():
    if f.status == "removed":
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
    You are an uncompromising senior engineer.

    Return exactly TEN bullet points:
      ✓ three good things
      ✗ seven problems

    Then ONE line:  FINAL SCORE: X/5   (1=terrible, 5=perfect)

    BEFORE ({f.filename})
    ---------------------
    {before}

    AFTER ({f.filename})
    --------------------
    {after}

    flake8 summary:
    {lint_text}
    """)

    resp = openai.ChatCompletion.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    tot_tokens += resp.usage.total_tokens
    sections.append(f"### {f.filename}\n{resp.choices[0].message.content.strip()}")

body = "\n\n---\n\n".join(sections) if sections else "_No code to review._"

match = re.search(r"FINAL\s+SCORE\s*:\s*([1-5])/5", body, re.I)
score = int(match.group(1)) if match else 1
if not match:
    body = ("⚠️ **Required `FINAL SCORE: X/5` line missing – auto-failing.**\n\n"
            + body)

event = "REQUEST_CHANGES" if (force_request or score <= FAIL_THRESHOLD) else "COMMENT"
ensure_label("needs-work" if event == "REQUEST_CHANGES" else "looks-good",
             "d93f0b" if event == "REQUEST_CHANGES" else "0e8a16")

pr.create_review(body=body, event=event)
print(f"✅ {event}  |  score {score}/5  |  tokens {tot_tokens}")

# expose summary
print(f"::set-output name=summary::" +
      json.dumps({"score": f"{score}/5", "event": event, "tokens": tot_tokens}))
