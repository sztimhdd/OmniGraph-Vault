-- Apply once after PRAGMA table_info confirms this column is absent.
ALTER TABLE accounts ADD COLUMN last_attempted_at TEXT;
