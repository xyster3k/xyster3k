# Private GitHub Metrics Plan

## Goal

Publish safe aggregate development metrics on the GitHub profile without exposing private repository names, commit messages, code, clients, or project details.

## Approach

1. Add a Python script that uses a GitHub token to read accessible repositories and pull requests.
2. Aggregate only safe fields:
   - active repositories count
   - commits authored by the profile user in the last 365 days
   - pull requests authored by the profile user in the last 365 days
   - public/private repository counts
   - language totals across accessible repositories
   - broad system-category tags derived from repository metadata, aggregated only as category counts
3. Generate `assets/private-metrics.json` and `assets/private-metrics.svg`.
4. Add a GitHub Action that runs daily and commits only those generated files.
5. Update the profile README to show the SVG and document that it is anonymized aggregate activity.

## Privacy Rules

- Do not publish private repository names.
- Do not publish private repository URLs.
- Do not publish commit messages.
- Do not publish branch names.
- Do not publish client/project names.
- Do not publish per-repository private stats.
- Do not require or store a token in the repository.

## Required User Setup

The repository owner must create a GitHub Actions secret named `GH_METRICS_TOKEN` with read access to the private repositories they want counted. The default `GITHUB_TOKEN` cannot read unrelated private repositories.
