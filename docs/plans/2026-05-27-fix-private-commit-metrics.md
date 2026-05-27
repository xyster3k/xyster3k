# Fix Private Commit Metrics Plan

## Goal

Fix the profile metrics card so the displayed commit count is an aggregate count of authored commits visible to the metrics token, not the limited GitHub contribution-graph commit count.

## Root Cause

The generator currently uses GraphQL `contributionsCollection.totalCommitContributions`. That value is not a raw count of all authored commits across accessible private repositories. The existing output shows `commits: 221` but `restricted_contributions: 3847`, which means most private activity is visible only as restricted contribution totals and is not being shown in the commit card.

## Approach

1. Keep repository names, URLs, commit messages, and branches out of generated assets.
2. Count commits with the GitHub commit search API using only aggregate `total_count` values.
3. Record whether GitHub reports incomplete search results, so bad counts can be diagnosed from the JSON without exposing private repository data.
4. Keep the GraphQL contribution count only as a diagnostic/fallback field.
5. Update the SVG labels and README wording so the card describes the metric accurately.
6. Validate syntax locally; the real private numbers will refresh in GitHub Actions because the token is only available there.
