# Database migrations

This is the migration directory specified by the project discussion. The current
local prototype bootstraps a new database with SQLAlchemy `Base.metadata.create_all`.
It does not upgrade an existing schema. Add and review versioned migrations here
before changing deployed database columns. No migration was needed for this folder
refactor because the table definitions and API contracts are unchanged.
