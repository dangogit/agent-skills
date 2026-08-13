# Lessons

- Use a `run: |` block for every multi-line GitHub Actions command. Never place
  heredoc lines below a scalar `run:` value because GitHub rejects the workflow
  before any job starts.
- Create review output folders with `mktemp -d`. Never clear a fixed temporary
  path before a review because the path may contain artifacts from another run.
