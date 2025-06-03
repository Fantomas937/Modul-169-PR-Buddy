"""
PR-Buddy v2
– posts a native GitHub review
– labels big PRs
– injects flake8 output into the prompt
– chunks large diffs to stay within token limits
"""

import os, textwrap, requests
from pathlib import Path
from github import Github
import openai

# ---------- config ----------
MODEL          = "gpt-4o-mini"       # adjust if needed
TEMPERATURE    = 0.2
MAX_PATCH_CHARS = 10_000             # per-chunk
BIG_PR_LINES   = 500                 # threshold for 'big-pr' label
# -----------------------------

# --- env & clients -------------------------------------------------
repo_full  = os.environ["GITHUB_REPOSITORY"]
pr_number  = int(os.environ["PR_NUMBER"])
gh_token   = os.environ["GITHUB_TOKEN"]
openai.api_key = os.environ["OPENAI_API_KEY"]

gh   = Github(gh_token)
repo = gh.get_repo(repo_full)
pr   = repo.get_pull(pr_number)

print(f"🔍 Reviewing PR #{pr_number} in {repo_full}")

# --- add size label -----------------------------------------------
if pr.additions + pr.deletions > BIG_PR_LINES:
    pr.add_to_labels("big-pr")
    print("🏷️  Added label 'big-pr'")

# --- read flake8 results (may be empty) ---------------------------
lint_path = Path("lint.txt")
lint_text = lint_path.read_text()[:4000] if lint_path.exists() else "No lint output."

# --- build review body --------------------------------------------
review_sections = []

for file in pr.get_files():
    if not file.patch:
        continue
    # chunk long patches
    for i in range(0, len(file.patch), MAX_PATCH_CHARS):
        chunk = file.patch[i : i + MAX_PATCH_CHARS]
        prompt = textwrap.dedent(f"""
        You are an expert code reviewer.
        File: {file.filename}
        Git diff chunk:\n{chunk}

        flake8 summary (ignore if irrelevant):
        {lint_text}

        Give concise bullet-point feedback, then a short rewritten snippet if improvements are obvious.
        """)
        resp = openai.ChatCompletion.create(
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        review_sections.append(f"### {file.filename}\n" + resp.choices[0].message.content.strip())

# Fallback if no patch was captured
if not review_sections:
    review_sections.append("No code changes with visible patch to review.")

review_body = "\n\n---\n\n".join(review_sections)

# --- post native review -------------------------------------------
pr.create_review(body=review_body, event="COMMENT")
print("✅ Review posted")

# (Optional) log token usage for cost tracking
try:
    usage = resp.usage  # last response
    print(f"Token usage: {usage.total_tokens} (prompt {usage.prompt_tokens} + completion {usage.completion_tokens})")
except AttributeError:
    pass
