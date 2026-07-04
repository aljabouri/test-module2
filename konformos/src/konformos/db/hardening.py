"""PostgreSQL hardening DDL — the DB-layer guards from Engineering Rules v1.1:

- INV-TL-01: trigger forbids UPDATE/DELETE on timeline_events (defense in
  depth under the application guard).
- INV-RP-02: partial unique index — at most one active pack per jurisdiction.
- INV-ORG-01: Row-Level Security on customer-scoped tables, keyed on the
  `app.current_org` session setting (FORCEd so even the table owner cannot
  bypass it; every session must set the org context).

Applied by migration 0002 on PostgreSQL only.
"""

HARDENING_STATEMENTS = [
    # INV-TL-01 — append-only timeline
    """
    CREATE OR REPLACE FUNCTION konformos_forbid_timeline_mutation()
    RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'INV-TL-01: timeline_events is append-only (no % allowed)', TG_OP;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE TRIGGER timeline_append_only
    BEFORE UPDATE OR DELETE ON timeline_events
    FOR EACH ROW EXECUTE FUNCTION konformos_forbid_timeline_mutation();
    """,
    # INV-RP-02 — one active pack per jurisdiction
    """
    CREATE UNIQUE INDEX uq_rule_packs_one_active_per_jurisdiction
    ON rule_packs (jurisdiction) WHERE status = 'active';
    """,
]

RLS_TABLES = ["properties", "users", "subscriptions"]

for _table in RLS_TABLES:
    HARDENING_STATEMENTS += [
        f"ALTER TABLE {_table} ENABLE ROW LEVEL SECURITY;",
        f"ALTER TABLE {_table} FORCE ROW LEVEL SECURITY;",
        f"""
        CREATE POLICY org_isolation_{_table} ON {_table}
        USING (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid);
        """,
    ]

HARDENING_DROP_STATEMENTS = [
    "DROP TRIGGER IF EXISTS timeline_append_only ON timeline_events;",
    "DROP FUNCTION IF EXISTS konformos_forbid_timeline_mutation();",
    "DROP INDEX IF EXISTS uq_rule_packs_one_active_per_jurisdiction;",
] + [
    stmt
    for table in RLS_TABLES
    for stmt in (
        f"DROP POLICY IF EXISTS org_isolation_{table} ON {table};",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
    )
]
