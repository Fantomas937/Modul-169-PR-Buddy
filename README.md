# PR-Buddy

## Project Description
PR-Buddy is an AI-powered tool that automates the review of pull requests. Its main goal is to leverage OpenAI models to provide insightful and constructive feedback on code changes, helping to improve code quality and streamline the review process.

## Features
- **AI-Powered Code Review**: Utilizes OpenAI models to analyze code changes and provide human-like feedback.
- **Configurable Review Strictness**: Allows customization of review strictness (temperature) and model choice to fit different project needs.
- **Identifies Good and Bad Aspects**: Highlights both positive contributions and areas for improvement in the changes.
- **Final Score**: Assigns a final score (X/5) to the pull request, summarizing the overall quality of the changes.
- **Automatic Labeling**: Automatically labels pull requests based on the review outcome (e.g., "big-pr", "needs-work", "looks-good").
- **Handles Removed Files**: Appropriately acknowledges and processes removed files in the review.
- **Linting Summary**: Provides a summary of linting output if available, integrating it into the overall review.

## Setup / Configuration

### Required Environment Variables
To use PR-Buddy, you need to set the following environment variables:
- `GITHUB_REPOSITORY`: The full name of the repository (e.g., `owner/repo`).
- `PR_NUMBER`: The number of the pull request being reviewed.
- `GITHUB_TOKEN`: A GitHub token with permissions to read repository content and write PR reviews/labels.
- `OPENAI_API_KEY`: Your OpenAI API key.

### Optional Configuration
Additional configuration options can be adjusted within the script:
- `MODEL`: The OpenAI model to use for reviews (e.g., "gpt-4", "gpt-3.5-turbo").
- `TEMPERATURE`: Controls the strictness/randomness of the AI's feedback.
- `MAX_CHARS_PER_SIDE`: Maximum characters to consider from each side of a diff.
- `BIG_PR_LINES`: Line threshold for labeling a PR as "big-pr".
- `FAIL_THRESHOLD`: Score threshold below which a PR is considered to need work.

## Usage
PR-Buddy is designed to be run in a GitHub Actions workflow. It will analyze the pull request specified by the environment variables and post a review comment with its findings and a final score.

For an example of how to integrate PR-Buddy into your workflow, please refer to the `.github/workflows/pr-buddy.yml` file in this repository.

## Contributing
Contributions are welcome! Please open an issue to discuss your ideas or submit a pull request with your improvements.

## License
This project is licensed under the MIT License. See the `LICENSE` file for details.