"""
One-time local fix. Run this once with:  python3 fix_local_migration_history.py

Background: migration 0005 got split into three (0005, 0005b, 0005a) to fix a
production deploy error. Your local db.sqlite3 already has the OLD (unsplit)
0005 recorded as applied, so Django doesn't know about the new 0005b/0005a
migration names and will complain about inconsistent migration history. This
script just records 0005b and 0005a as already-applied in your local
database's migration bookkeeping table (django_migrations) — it does NOT
touch any actual table, column, or data. Safe to run once, safe to re-run.
"""
import sqlite3

con = sqlite3.connect("db.sqlite3")
cur = con.cursor()

cur.execute(
    "SELECT applied FROM django_migrations WHERE app='marks' AND name='0006_remove_groupcategoryconfig_subjects_and_more'"
)
row = cur.fetchone()
if row is None:
    print("Could not find migration 0006 in this database — nothing to fix, or wrong db file.")
else:
    ts = row[0]
    for name in ("0005b_backfill_exam_category_fields", "0005a_finalize_exam_category_fields"):
        cur.execute(
            "SELECT COUNT(*) FROM django_migrations WHERE app='marks' AND name=?", (name,)
        )
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO django_migrations (app, name, applied) VALUES (?, ?, ?)",
                ("marks", name, ts),
            )
            print(f"Fixed: recorded {name} as applied.")
        else:
            print(f"{name} already recorded, no change made.")
    con.commit()

print()
print("Current marks migration history:")
for row in cur.execute("SELECT name, applied FROM django_migrations WHERE app='marks' ORDER BY applied"):
    print(" ", row)

con.close()
