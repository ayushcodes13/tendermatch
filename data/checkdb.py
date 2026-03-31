import sqlite3

conn = sqlite3.connect("data/tenders.db")
cursor = conn.cursor()

# 1. Total count
cursor.execute("SELECT COUNT(*) FROM tenders")
print("Total rows:", cursor.fetchone()[0])

# 2. Sample rows
cursor.execute("""
SELECT tender_id, title, organization, is_blocked, has_signal
FROM tenders
LIMIT 10
""")

rows = cursor.fetchall()

for r in rows:
    print(f"""
TITLE: {r[1]}
ORG: {r[2]}
BLOCKED: {r[3]}
SIGNAL: {r[4]}
-------------------
""")

# 3. Category counts
cursor.execute("SELECT COUNT(*) FROM tenders WHERE is_blocked=1")
blocked = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM tenders WHERE is_blocked=0 AND has_signal=0")
low_signal = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM tenders WHERE has_signal=1")
high_signal = cursor.fetchone()[0]

print("\n--- DISTRIBUTION ---")
print({
    "blocked": blocked,
    "low_signal": low_signal,
    "high_signal": high_signal
})