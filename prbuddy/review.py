"""
PR-Buddy: An AI-powered GitHub Pull Request reviewer using OpenAI.

PR-Buddy v6  – strict, full-context reviewer
Outputs ten concise bullets (✓ good / ✗ bad) and FINAL SCORE: X/5
"""

import os, re, textwrap, json
from pathlib import Path
from github import Github
import openai

# ─── CONFIG ─────────────────────────────────────────────────────────
MODEL              = "gpt-4.1"      # The OpenAI model used for review. swap to gpt-4.1 when available
TEMPERATURE        = 0.2            # Controls the randomness/strictness of the review.
MAX_CHARS_PER_SIDE = 20_000        # Maximum characters to consider for each side of the diff (before/after).
BIG_PR_LINES       = 400            # Threshold for labeling a PR as "big-pr".
FAIL_THRESHOLD     = 4              # Score at or below which the PR is marked as "needs-work" and changes are requested.
# ────────────────────────────────────────────────────────────────────

# Retrieve environment variables
GITHUB_REPOSITORY  = os.environ["GITHUB_REPOSITORY"]  # Full name of the repository (e.g., "owner/repo")
PR_NUMBER          = int(os.environ["PR_NUMBER"])   # Number of the pull request being reviewed
GITHUB_TOKEN       = os.environ["GITHUB_TOKEN"]       # GitHub token for API access
OPENAI_API_KEY     = os.environ["OPENAI_API_KEY"]     # OpenAI API key

# Initialize GitHub and OpenAI clients
openai.api_key = OPENAI_API_KEY
gh   = Github(GITHUB_TOKEN)
repo = gh.get_repo(GITHUB_REPOSITORY)
pr   = repo.get_pull(PR_NUMBER)
print(f"🔎 Reviewing PR #{PR_NUMBER} in {GITHUB_REPOSITORY}")

def ensure_label(name, color="ededed"):
    """
    Ensures a label exists on the PR. Creates the label in the repository if it doesn't exist.
    Args:
        name (str): The name of the label.
        color (str, optional): The color of the label (hex without #). Defaults to "ededed".
    """
    if name not in [l.name for l in pr.get_labels()]:
        try:
            repo.get_label(name) # Check if label exists in repo
        except Exception:
            repo.create_label(name, color) # Create if not
        pr.add_to_labels(name) # Add label to PR

# Size labeling: Apply "big-pr" label if changes exceed BIG_PR_LINES.
if sum(f.changes for f in pr.get_files()) > BIG_PR_LINES:
    ensure_label("big-pr", "f9d0c4")

# Force request changes mechanism:
# If files in prbuddy/ directory are changed with more deletions than additions,
# it implies a potential issue with the reviewer itself, so force a "REQUEST_CHANGES".
force_request = False
for f in pr.get_files():
    if f.filename.startswith("prbuddy/") and f.deletions > f.additions:
        ensure_label("needs-work", "d93f0b")
        force_request = True
        break

# Read linting output if available, truncate to first 4000 chars.
lint_text = Path("lint.txt").read_text()[:4000] if Path("lint.txt").exists() else "No lint output."

sections, tot_tokens = [], 0
# Process each file in the pull request.
for f in pr.get_files():
    # Skip removed files as there's no "after" content to review.
    if f.status == "removed":
        continue
    try:
        # Fetch content of the file from the base branch (before changes).
        before = repo.get_contents(f.filename, ref=pr.base.sha).decoded_content.decode()
    except Exception:
        # If fetching base content fails (e.g., new file), use empty string.
        before = ""
    try:
        # Fetch content of the file from the head branch (after changes).
        after = repo.get_contents(f.filename, ref=pr.head.sha).decoded_content.decode()
    except Exception:
        # If fetching head content fails (should be rare), use the patch data as a fallback.
        after = f.patch or ""

    # Truncate file contents to MAX_CHARS_PER_SIDE to manage token usage.
    before, after = before[:MAX_CHARS_PER_SIDE], after[:MAX_CHARS_PER_SIDE]

    # Construct the prompt for the OpenAI API.
    # System message sets the role and expectations for the AI.
    # Includes "before" and "after" code snippets and lint summary for context.
    prompt = textwrap.dedent(f"""
    You are an uncompromising senior engineer that checks Github pull requests.

    Then ONE about the code change line:  FINAL SCORE: X/5   (1=terrible, 5=perfect)
    Your goal is to be critical about the codes and look if the changes are actualy good from the last code.
    Describe these changes 

    BEFORE ({f.filename})
    ---------------------
    {before}

    AFTER ({f.filename})
    --------------------
    {after}

    flake8 summary:
    {lint_text}
    """)

    # Call the OpenAI ChatCompletion API.
    # Uses the specified MODEL and TEMPERATURE.
    resp = openai.ChatCompletion.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    tot_tokens += resp.usage.total_tokens
    # Extract the review content from the API response.
    sections.append(f"### {f.filename}\n{resp.choices[0].message.content.strip()}")

# Combine review sections for all files, or use a default message if no files were reviewed.
body = "\n\n---\n\n".join(sections) if sections else "_No code to review._"

# Extract the final score from the review body using regex.
# Searches for "FINAL SCORE: X/5" (case-insensitive).
match = re.search(r"FINAL\s+SCORE\s*:\s*([1-5])/5", body, re.I)
score = int(match.group(1)) if match else 1 # Default to 1 if score not found.
if not match:
    # If the score line is missing, prepend a warning to the review body.
    body = ("⚠️ **Required `FINAL SCORE: X/5` line missing – auto-failing.**\n\n"
            + body)

# Determine the review event type based on the score and force_request flag.
# REQUEST_CHANGES if forced or if the score is at or below FAIL_THRESHOLD.
event = "REQUEST_CHANGES" if (force_request or score <= FAIL_THRESHOLD) else "COMMENT"

# Apply "needs-work" or "looks-good" label based on the review event.
ensure_label("needs-work" if event == "REQUEST_CHANGES" else "looks-good",
             "d93f0b" if event == "REQUEST_CHANGES" else "0e8a16")

# Create the review comment on the pull request.
pr.create_review(body=body, event=event)
print(f"✅ {event}  |  score {score}/5  |  tokens {tot_tokens}")

# Set GitHub Action output: Expose review summary data (score, event, tokens)
# to be used by subsequent steps in the GitHub Actions workflow.
print(f"::set-output name=summary::" +
      json.dumps({"score": f"{score}/5", "event": event, "tokens": tot_tokens}))
