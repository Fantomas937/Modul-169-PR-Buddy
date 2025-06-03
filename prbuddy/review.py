"""
PR-Buddy v3-strict
• Native GitHub review (COMMENT or REQUEST_CHANGES)
• Adds:  big-pr · needs-work · looks-good  labels
• Includes flake8 output
• Scores quality 1-5; score ≤ 4 ⇒ REQUEST_CHANGES
• Flags net deletions in prbuddy/ as needs-work
• Chunks large diffs to stay under token limits
"""

import os, re, textwrap, requests
from pathlib import Path
from github import Github
import openai

# ─── configuration ────────────────────────────────────────────────
MODEL             = "gpt-4.1"    # swap to "gpt-4o" if available
TEMPERATURE       = 0.0              # deterministic & strict
MAX_PATCH_CHARS   = 10_000           # per chunk
BIG_PR_LINES      = 400              # touched-lines threshold
RUBRIC_THRESHOLD  = 4                # ≤4 → request changes
# ───────────────────────────────────────────────────────────────────

repo_full  = os.environ["GITHUB_REPOSITORY"]
pr_number  = int(os.environ["PR_NUMBER"])
gh_token   = os.environ["GITHUB_TOKEN"]
openai.api_key = os.environ["OPENAI_API_KEY"]

gh   = Github(gh_token)
repo = gh.get_repo(repo_full)
pr   = repo.get_pull(pr_number)
print(f"👀 Reviewing PR #{pr_number} in {repo_full}")

# -- utility: ensure a label exists & applied ----------------------
def ensure_label(name: str, color: str = "ededed"):
    if name not in [l.name for l in pr.get_labels()]:
        try:
            repo.get_label(name)
        except Exception:
            repo.create_label(name, color)
        pr.add_to_labels(name)
        print(f"🏷️  Added label '{name}'")

# -- heuristics ----------------------------------------------------
touched = sum(f.changes for f in pr.get_files())
if touched > BIG_PR_LINES:
    ensure_label("big-pr", "f9d0c4")

force_request = False
for f in pr.get_files():
    if f.filename.startswith("prbuddy/") and f.deletions > f.additions:
        ensure_label("needs-work", "d93f0b")
        force_request = True
        break

# -- lint context --------------------------------------------------
lint_text = Path("lint.txt").read_text()[:4000] if Path("lint.txt").exists() else "No lint output."

# -- build review --------------------------------------------------
sections, total_tokens = [], 0
for file in pr.get_files():
    if not file.patch:
        continue
    for i in range(0, len(file.patch), MAX_PATCH_CHARS):
        chunk = file.patch[i : i + MAX_PATCH_CHARS]
        prompt = textwrap.dedent(f"""
        ROLE: senior staff engineer.

        Evaluate the Git diff chunk below.

        • Bullet-list concrete issues: logic, style, tests, security.
        • Suggest actionable fixes.
        • Be STRICT; flag regressions or unclear code.
        • Finish with exactly one line:  SCORE: X/5
          (1=awful, 3=barely acceptable, 5=excellent).

        FILE: {file.filename}

        --- PATCH ---
        {chunk}
        --- END PATCH ---

        flake8 summary (ignore if irrelevant):
        {lint_text}
        """)

        resp = openai.ChatCompletion.create(
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        total_tokens += resp.usage.total_tokens
        sections.append(f"### {file.filename}\n{resp.choices[0].message.content.strip()}")

if not sections:
    sections.append("_No patch to review._")

body = "\n\n---\n\n".join(sections)

score_match = re.search(r"SCORE:\s*([1-5])/5", body)
score = int(score_match.group(1)) if score_match else RUBRIC_THRESHOLD
print(f"Raw rubric score: {score}  |  Tokens used: {total_tokens}")

if force_request or score <= RUBRIC_THRESHOLD:
    event = "REQUEST_CHANGES"
    ensure_label("needs-work", "d93f0b")
else:
    event = "COMMENT"
    ensure_label("looks-good", "0e8a16")

pr.create_review(body=body, event=event)
print(f"✅ Posted {event} review")
