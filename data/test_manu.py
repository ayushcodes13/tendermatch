import json
from collections import Counter

with open("data/manufacturers.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Manufacturers:", len(data))
print("Names:")
for m in data:
    print("-", m["name"])

ids = [m["id"] for m in data]
dupes = [k for k, v in Counter(ids).items() if v > 1]
print("Duplicate IDs:", dupes if dupes else "None")