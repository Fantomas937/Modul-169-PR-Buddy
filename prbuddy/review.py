"""
Very first skeleton of PR-Buddy.
Fetches the diff of the current PR, asks OpenAI for a review,
and posts the result back as a comment.
"""
import os, requests
from github import Github
import openai

# --- 1. Inputs & setup -------------------------------------------------------
repo_fullname = os.environ["GITHUB_REPOSITORY"]          # e.g. Fantomas937/Modul-169-PR-Buddy
pr_number      = int(os.environ["PR_NUMBER"])
gh_token       = os.environ["GITHUB_TOKEN"]              # auto-injected by Actions
openai.api_key = os.environ["OPENAI_API_KEY"]

g      = Github(gh_token)
repo   = g.get_repo(repo_fullname)
pr     = repo.get_pull(pr_number)

# --- 2. Grab the unified diff (patch) ----------------------------------------
patch_text = requests.get(pr.patch_url, headers={"Authorization": f"token {gh_token}"}).text
# Trim huge diffs so we stay within token limits
patch_snippet = patch_text[:12000]

# --- 3. Ask OpenAI for a review ----------------------------------------------
prompt = f"Please review the following Git diff and suggest improvements:\n\n{patch_snippet}"
resp   = openai.ChatCompletion.create(
            model="gpt-4o-mini",   # or any model you have access to
            messages=[{"role": "user", "content": prompt}]
         )
comment_body = resp.choices[0].message.content.strip()

# --- 4. Post the comment back to the PR --------------------------------------
pr.create_issue_comment(comment_body)
print("✅ Review posted")
