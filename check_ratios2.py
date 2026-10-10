import json
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "data.js"
t = open(path, encoding="utf-8").read()
data, _ = json.JSONDecoder().raw_decode(t[t.index("["):])
multi = [x for x in data if len(x["ch"]) >= 2]
ratio = lambda x: max(x["ch"].values()) / min(x["ch"].values())
bad = [x for x in multi if ratio(x) > 5]
print("товаров:", len(data), "| разброс >5x:", len(bad), "| >2x:", sum(ratio(x) > 2 for x in multi))
print("длина кода у >5x:", Counter(len(x["c"]) for x in bad))
print("первая цифра у >5x:", Counter(x["c"][0] for x in bad).most_common(6))
for x in sorted(bad, key=ratio, reverse=True)[:14]:
    print(x["c"], x["n"][:25], "|", x["s"], "|", x["ch"])
