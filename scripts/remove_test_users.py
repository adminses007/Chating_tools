"""Remove test users alice and bob."""
import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parent.parent / "data" / "chat.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()

print("BEFORE:")
for r in cur.execute("SELECT id, username, display_name, role FROM users ORDER BY id"):
    print(dict(r))

rows = list(
    cur.execute(
        "SELECT id, username FROM users WHERE lower(username) IN ('alice', 'bob')"
    )
)
print("TO_DELETE:", [dict(r) for r in rows])
ids = [r["id"] for r in rows]

for uid in ids:
    cids = [
        r[0]
        for r in cur.execute(
            "SELECT conversation_id FROM conversation_members WHERE user_id = ?",
            (uid,),
        )
    ]
    cur.execute("DELETE FROM users WHERE id = ?", (uid,))
    print("deleted user", uid)
    for cid in cids:
        n = cur.execute(
            """
            SELECT COUNT(*) FROM conversation_members
            WHERE conversation_id = ? AND left_at IS NULL
            """,
            (cid,),
        ).fetchone()[0]
        if n < 2:
            cur.execute("DELETE FROM conversations WHERE id = ?", (cid,))
            print("deleted conversation", cid)

conn.commit()
print("AFTER:")
for r in cur.execute("SELECT id, username, display_name, role FROM users ORDER BY id"):
    print(dict(r))
conn.close()
print("done")
