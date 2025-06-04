# PR-Buddy Feature Ideas

## Feature Idea 1: Customizable Review Focus

- **Status:** Implemented
- **Description:** Allow users to specify areas of focus for the review via configuration in the workflow file or special comments in the PR description (e.g., `#prbuddy_focus: performance, security`). PR-Buddy would then tailor its review prompt to emphasize these aspects.
- **Benefit:** Provides more targeted and relevant reviews based on PR-specific concerns.

## Feature Idea 2: Security Vulnerability Check

- **Status:** Implemented
- **Description:** Integrate with a lightweight, open-source security scanner (or use a specialized prompt for OpenAI) to identify potential common security vulnerabilities (e.g., OWASP Top 10 related, hardcoded secrets).
- **Benefit:** Adds a layer of automated security screening to the review process.

## Feature Idea 3: Suggest Code Snippets

- **Status:** Implemented
- **Description:** Enhance the OpenAI prompt to not only identify issues but also to suggest specific code snippets for improvements where applicable (e.g., for fixing a bug or optimizing a small piece of code). These suggestions would be clearly marked as AI-generated.
- **Benefit:** Makes the review more actionable and helps developers fix issues faster.
