"""
PR-Buddy v3

• Native GitHub review (COMMENT or REQUEST_CHANGES)
• Adds 'big-pr', 'needs-work', 'looks-good' labels
• Injects flake8 output for context
• Scores quality 1-5; ≤3 → request changes
• Flags net deletions to prbuddy/ as needs-work
• Chunks huge diffs to stay under token limits
"""

import os, re, textwrap, requests
from pathlib import Path
from github import Github
import openai

# ─── Config ──────────────────────────────────────────────────────────
MODEL             = "gpt-4o-mini"   # switch to "gpt-4o" if you have access
TEMPERATURE       = 0.2
MAX_PATCH_CHARS   = 10_000          # per diff chunk sent to OpenAI
BIG_PR_LINES      = 400             # touched-lines ⇒ 'big-pr' label
RUBRIC_THRESHOLD  = 3               # ≤3 forces REQUEST_CHANGES
# ─────────────────────────────────────────────────────────────────────

# --- Environment / clients ------------------------------------------
repo_full  = os.environ["GITHUB_REPOSITORY"]   # e.g. Fantomas937/Modul-169-PR-Buddy
pr_number  = int(os.environ["PR_NUMBER"])
gh_token   = os.environ["GITHUB_TOKEN"]
openai.api_key = os.environ["OPENAI_API_KEY"]

gh   = Github(gh_token)
repo = gh.get_repo(repo_full)
pr   = repo.get_pull(pr_number)
print(f"📋 Reviewing PR #{pr_number} in {repo_full}")

# --- Helper: add label once -----------------------------------------
def ensure_label(name: str):
    if name not in [l.name for l in pr.get_labels()]:
        pr.add_to_labels(name)
        print(f"🏷️  Added label '{name}'")

# --- Heuristics: big PR & downgrades --------------------------------
touched = sum(f.changes for f in pr.get_files())
if touched > BIG_PR_LINES:
    ensure_label("big-pr")

force_request = False
for f in pr.get_files():
    if f.filename.startswith("prbuddy/") and f.deletions > f.additions:
        ensure_label("needs-work")
        force_request = True
        print("⚠️  Net deletions in prbuddy/ detected")
        break

# --- Lint context ---------------------------------------------------
lint_text = Path("lint.txt").read_text()[:4000] if Path("lint.txt").exists() else "No lint output."

# --- Build review sections -----------------------------------------
sections = []
for file in pr.get_files():
    if not file.patch:        # binary or deleted
        continue
    for i in range(0, len(file.patch), MAX_PATCH_CHARS):
        chunk = file.patch[i : i + MAX_PATCH_CHARS]

        prompt = textwrap.dedent(f"""
        You are an expert software reviewer.

        TASK:
        • Bullet feedback on the diff chunk below.
        • End with EXACTLY one line:  SCORE: X/5  (1=terrible … 5=excellent).

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

        sections.append(f"### {file.filename}\n{resp.choices[0].message.content.strip()}")
        print(f"Tokens ({file.filename}): {resp.usage.total_tokens}")

if not sections:
    sections.append("_No visible patch to review._")

body = "\n\n---\n\n".join(sections)

# --- Parse rubric score --------------------------------------------
m = re.search(r"SCORE:\s*([1-5])/5", body)
score = int(m.group(1)) if m else RUBRIC_THRESHOLD
print(f"Rubric score: {score}/5")

# --- Decide event & labels -----------------------------------------
if force_request or score <= RUBRIC_THRESHOLD:
    event = "REQUEST_CHANGES"
    ensure_label("needs-work")
else:
    event = "COMMENT"
    ensure_label("looks-good")

# --- Post review ----------------------------------------------------
pr.create_review(body=body, event=event)
print(f"✅ Posted review with event '{event}'")
