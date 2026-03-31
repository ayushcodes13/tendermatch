from data.db import get_connection, get_high_signal_matches

conn = get_connection()

results = get_high_signal_matches(conn)

print("\n🔥 TOP MATCHES FROM DB:\n")

for r in results:
    print(r)