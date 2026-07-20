# Quality Inventory

Run `python scripts/quality_inventory.py --root .` to produce the current inventory.

The migration repaired the persistence, auth, event-store, repository, knowledge-schema, and visual-generator paths to UTF-8/ASCII source text. The current inventory is expected to report no encoding-risk or trivially unreachable statements.

The inventory also reports statements that follow an unconditional `return`, `raise`, `break`, or `continue` in Python blocks. It is diagnostic-only so every finding can be reviewed before deletion. CI runs it to keep the debt visible while lint treats historical frontend type debt as warnings rather than build failures.
