import json
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "data.js"
text = open(path, encoding="utf-8").read()
data, _ = json.JSONDecoder().raw_decode(text[text.index("["):])

print("товаров:", len(data))
letters = Counter((x["n"].strip() or "?")[0] for x in data)
heb = "אבגדהוזחטיכלמנסעפצקרשת"
print("букв иврита с товарами: %d из %d" % (sum(1 for c in heb if letters.get(c)), len(heb)))
print("нет товаров на буквы:", [c for c in heb if not letters.get(c)])

multi = [x for x in data if len(x["ch"]) >= 2]
ratios = sorted(
    ((max(x["ch"].values()) / min(x["ch"].values()), x) for x in multi),
    key=lambda t: -t[0],
)
print("мин. цена:", min(min(x["ch"].values()) for x in data))
print("разброс > 5x: %d, > 2x: %d" % (sum(r > 5 for r, _ in ratios), sum(r > 2 for r, _ in ratios)))
print("топ-8 по разбросу:")
for r, x in ratios[:8]:
    print("  %.1fx  %s | %s | %s" % (r, x["n"][:35], x["s"], x["ch"]))
