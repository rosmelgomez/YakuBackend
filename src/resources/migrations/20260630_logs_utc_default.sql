ALTER TABLE logs_sistema
    ALTER COLUMN fecha SET DEFAULT (now() AT TIME ZONE 'utc');
