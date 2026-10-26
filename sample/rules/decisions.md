# Decision rules (placeholder, v0)

The insights layer reads these rules when it looks for decisions Granola missed.
Nothing is analyzed until `enabled` is true in `settings.json`. Rules come later;
editing this file or settings.json marks every insight stale, and the next run
re-analyzes only those.

Planned topics for the real rules:
- what counts as a decision versus discussion
- what makes a decision "key" (big meetings, people, budget, allocation, client commitments)
- what to ignore
