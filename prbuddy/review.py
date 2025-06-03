"""
PR-Buddy v3
– runs inside a GitHub Action
– posts a native review or requests changes
– adds 'big-pr', 'needs-work', 'looks-good' labels
– injects flake8 output for context
– scores quality 1-5 and acts on it
– chunks large diffs to stay within token limits
"""

import os, re, textwrap, requests
from pathlib import Path
from github import Github
import openai

# ---------- configuration ----------
MODEL             = "gpt-4o-mini"
TEMPERATURE       = 0.2
MAX_PATCH_CHARS   = 10_000     # per chunk
BIG_PR_LINES      = 400        # touched lines threshold for big-pr label
RUBRIC_THRESHOLD  = 3          # <=3 triggers request-changes
# -----------------------------------

# --- environment & clients ----------------------------------------
repo_full  = os.environ["GITHUB_REPOSITORY"]          # e.g. Fantomas937/Modul-169-PR-Buddy
pr_number  = int(os.environ["PR_NUMBER"])
gh_token   = os.environ["GITHUB_TOKEN"]
openai.api_key = os.environ["OPENAI_API_KEY"]

gh   = Github(gh_token)
repo = gh.get_repo(repo_full)
pr   = repo.get_pull(pr_number)

print(f"📋 Reviewing PR #{pr_number} in {repo_full}")

# --- helper to add a label only once ------------------------------
def ensure_label(label: str):
    if label not in [l.name for l in pr.get_labels()]:
        pr.add_to_labels(label)
        print(f"🏷️  Added label '{label}'")

# --- size / downgrade heuristics ----------------------------------
touched_lines = sum(f.changes for f in pr.get_files())
if touched_lines > BIG_PR_LINES:
    ensure_label("big-pr")

force_request_changes = False
for f in pr.get_files():
    if f.filename.startswith("prbuddy/") and f.deletions > f.additions:
        ensure_label("needs-work")
        force_request_changes = True
        print("⚠️  Detected net deletions in prbuddy/, flagging needs-work")
        break

# --- flake8 context -----------------------------------------------
lint_text = Path("lint.txt").read_text()[:4000] if Path("lint.txt").exists() else "No lint output."

# --- collect review sections --------------------------------------
review_sections = []

for file in pr.get_files():
    if not file.patch:
        continue
    for i in range(0, len(file.patch), MAX_PATCH_CHARS):
        chunk = file.patch[i : i + MAX_PATCH_CHARS]

        prompt = textwrap.dedent(f"""
        You are an expert software reviewer.

        TASK:
        1. Provide bullet-point feedback on the Git diff chunk below.
        2. End with **exactly one line** of the form  `SCORE: X/5`
           where X is an integer (1 = terrible, 3 = acceptable, 5 = excellent).

        FILE: {file.filename}

        --- PATCH START ---
        {chunk}
        --- PATCH END ---

        flake8 summary (ignore if irrelevant):
        {lint_text}
        """)

        resp = openai.ChatCompletion.create(
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )

        review_sections.append(f"### {file.filename}\n{resp.choices[0].message.content.strip()}")
        usage = resp.usage
        print(f"Token usage ({file.filename}): {usage.total_tokens}")

if not review_sections:
    review_sections.append("_No visible patch to review._")

review_body = "\n\n---\n\n".join(review_sections)

# --- extract rubric score -----------------------------------------
m = re.search(r"SCORE:\s*([1-5])/5", review_body)
score = int(m.group(1)) if m else RUBRIC_THRESHOLD  # default neutral

print(f"Derived score: {score}/5")

# --- decide review type & labels ----------------------------------
if force_request_changes or score <= RUBRIC_THRESHOLD:
    event = "REQUEST_CHANGES"
    ensure_label("needs-work")
else:
    event = "COMMENT"
    ensure_label("looks-good")

# --- post review ---------------------------------------------------
pr.create_review(body=review_body, event=event)
print(f"✅ Posted review with event '{event}'")
