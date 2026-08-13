# Lessons

- Use a `run: |` block for every multi-line GitHub Actions command. Never place
  heredoc lines below a scalar `run:` value because GitHub rejects the workflow
  before any job starts.
