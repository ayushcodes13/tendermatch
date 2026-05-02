"""
Ad-hoc database query debugger.

Purpose:
Quickly retrieves the latest high-signal matches from the database to verify 
joined table results and match scoring persistence.
"""
from data.db import get_connection, get_high_signal_matches

conn = get_connection()

results = get_high_signal_matches(conn)

print("\n🔥 TOP MATCHES FROM DB:\n")

for r in results:
    print(r)