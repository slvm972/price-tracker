"""
make_viewer.py — читает данные из SQLite и создаёт price_viewer.html.

Новое: переключение языков иврит / русский.
Выбор языка сохраняется в localStorage.
При переключении на русский — интерфейс переходит на LTR (слева направо).
"""

import json, time
import database

print("Читаем данные из базы данных...")
database.init_db()

rows = database.get_latest_prices(limit=500_000)

if not rows:
    print("База данных пуста!")
    print("Сначала запустите: python download_all.py")
    exit(1)

catalog_by_barcode = {}
for row in rows:
    barcode = row["barcode"]
    retailer = row["retailer"]
    price = row["price"]
    previous_price = row.get("previous_price")
    if barcode not in catalog_by_barcode:
        catalog_by_barcode[barcode] = {
            "c": barcode,
            "n": row["name"],
            "m": row["brand"] or "",
            "s": row["size"] or "",
            "ch": {},
            "prev": {},
        }
    existing = catalog_by_barcode[barcode]["ch"].get(retailer)
    if existing is None or price < existing:
        catalog_by_barcode[barcode]["ch"][retailer] = price
        if previous_price is not None:
            catalog_by_barcode[barcode]["prev"][retailer] = previous_price

catalog = list(catalog_by_barcode.values())

from collections import Counter

chain_counts = Counter()
for item in catalog:
    for ch in item["ch"]:
        chain_counts[ch] += 1
chains_found = [ch for ch, _ in chain_counts.most_common()]

in_multiple = sum(1 for r in catalog if len(r["ch"]) >= 2)
print(f"  Уникальных штрихкодов: {len(catalog):,}")
print(f"  Товаров в 2+ сетях:    {in_multiple:,}")
print(f"  Сети: {', '.join(chains_found)}")

CHAIN_COLORS = {
    "Victory": "#58a6ff",
    "Shufersal": "#ff7b72",
    "Yohananof": "#ffa657",
    "Osher Ad": "#3fb950",
    "Tiv Taam": "#d2a8ff",
    "Hazi Hinam": "#79c0ff",
    "YaynoeBitan": "#f0883e",
    "Keshet": "#56d364",
    "Rami Levy": "#ff6e96",
}

D = json.dumps(catalog, ensure_ascii=False)
C = json.dumps(
    {ch: CHAIN_COLORS.get(ch, "#8b949e") for ch in chains_found}, ensure_ascii=False
)
CH = json.dumps(chains_found, ensure_ascii=False)
UPD = time.strftime("%d.%m.%Y %H:%M")
stats = database.get_db_stats()

# ── Все строки интерфейса на двух языках ──────────────────────────
# Добавить новый язык = добавить новый объект в LANG в JS ниже

html = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>🛒 השוואת מחירים / Сравнение цен</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Hebrew:wght@300;400;600;700&family=Noto+Sans:wght@300;400;600;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0d1117;--surf:#161b22;--surf2:#21262d;--brd:#30363d;--txt:#e6edf3;--dim:#8b949e;--acc:#58a6ff;--grn:#3fb950;--red:#ff7b72;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--txt);font-family:'Noto Sans Hebrew',sans-serif;min-height:100vh;}
body.ltr{font-family:'Noto Sans',sans-serif;}

/* ── Header ── */
header{background:var(--surf);border-bottom:1px solid var(--brd);padding:12px 20px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:200;flex-wrap:wrap;}
.logo{font-family:'Space Mono',monospace;font-size:.9rem;color:var(--acc);white-space:nowrap;flex-shrink:0;}.logo b{color:var(--grn);}
.sw{flex:1;min-width:200px;max-width:500px;position:relative;}
#q{width:100%;padding:9px 14px 9px 40px;background:var(--surf2);border:1px solid var(--brd);border-radius:8px;color:var(--txt);font-size:1rem;outline:none;transition:border-color .2s,box-shadow .2s;font-family:inherit;}
body.ltr #q{padding:9px 40px 9px 14px;}
#q:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(88,166,255,.1);}#q::placeholder{color:var(--dim);}
.qi{position:absolute;left:12px;top:50%;transform:translateY(-50%);pointer-events:none;}
body.ltr .qi{left:auto;right:12px;}
.hs{font-family:'Space Mono',monospace;font-size:.68rem;color:var(--dim);line-height:1.8;}.hs b{color:var(--grn);}

/* ── Language switcher ── */
.lang-sw{display:flex;gap:4px;margin-right:auto;flex-shrink:0;}
body.ltr .lang-sw{margin-right:0;margin-left:auto;}
.lang-btn{padding:4px 10px;border-radius:6px;border:1px solid var(--brd);background:var(--surf2);color:var(--dim);font-size:.8rem;cursor:pointer;transition:all .15s;font-weight:600;letter-spacing:.03em;}
.lang-btn:hover{border-color:var(--acc);color:var(--txt);}
.lang-btn.active{background:var(--acc);border-color:var(--acc);color:#0d1117;}

/* ── Chain selector ── */
#chain-panel{background:var(--surf);border-bottom:2px solid var(--brd);padding:11px 20px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.chain-btn{display:flex;align-items:center;gap:6px;padding:5px 12px;border-radius:8px;cursor:pointer;border:2px solid var(--brd);background:var(--surf2);font-size:.8rem;color:var(--dim);transition:all .18s;user-select:none;font-family:inherit;}
.chain-btn:hover{border-color:#555;color:var(--txt);}
.chain-btn.active{font-weight:700;}
.chain-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;}
.chain-count{font-size:.65rem;opacity:.7;margin-right:2px;}
body.ltr .chain-count{margin-right:0;margin-left:2px;}
#chain-all{padding:5px 12px;border-radius:8px;border:1px dashed var(--brd);background:transparent;color:var(--dim);font-size:.75rem;cursor:pointer;transition:all .15s;font-family:inherit;}
#chain-all:hover{border-color:var(--acc);color:var(--acc);}
.chain-tip{font-size:.68rem;color:var(--dim);margin-right:auto;}
body.ltr .chain-tip{margin-right:0;margin-left:auto;}

/* ── Controls bar ── */
.bar{padding:9px 20px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--brd);background:var(--bg);}
.lbl{font-size:.73rem;color:var(--dim);}
.chip,.sb{padding:4px 12px;background:var(--surf2);border:1px solid var(--brd);border-radius:16px;font-size:.76rem;cursor:pointer;transition:all .15s;user-select:none;color:var(--dim);font-family:inherit;}
.chip:hover,.sb:hover{border-color:var(--acc);color:var(--txt);}
.chip.on{background:var(--acc);border-color:var(--acc);color:#0d1117;font-weight:700;}
.sb.on{border-color:var(--acc);color:var(--acc);}
.div{width:1px;height:18px;background:var(--brd);flex-shrink:0;}
.vb{padding:4px 11px;background:var(--surf2);border:1px solid var(--brd);border-radius:6px;cursor:pointer;color:var(--dim);font-size:.77rem;transition:all .15s;font-family:inherit;}
.vb.on{border-color:var(--acc);color:var(--acc);background:var(--surf);}

/* ── Grid ── */
#res.gv{padding:16px 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:11px;}
.card{background:var(--surf);border:1px solid var(--brd);border-radius:10px;padding:13px;display:flex;flex-direction:column;gap:8px;transition:border-color .2s,transform .15s;animation:fi .2s ease both;}
.card:hover{border-color:var(--acc);transform:translateY(-2px);}
@keyframes fi{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
.cn{font-size:.88rem;font-weight:500;line-height:1.45;}
.price-row{display:flex;flex-wrap:wrap;gap:5px;margin-top:2px;}
.price-cell{flex:1;min-width:105px;padding:7px 9px;border-radius:7px;border:1px solid var(--brd);}
.price-cell.best{border-color:var(--grn);background:rgba(63,185,80,.07);}
.pc-chain{font-size:.65rem;font-weight:700;margin-bottom:3px;}
.pc-price{font-family:'Space Mono',monospace;font-size:1.1rem;font-weight:700;}
.pc-unit{font-size:.63rem;color:var(--dim);margin-top:1px;}
.pc-diff{font-size:.75rem;font-weight:500;margin-top:2px;color:var(--dim);}
.pc-diff.up{color:#da3633;}
.pc-diff.down{color:#3fb950;}
.saving{font-size:.7rem;color:var(--grn);margin-top:3px;}

/* ── Compare ── */
#res.cv{padding:16px 20px;display:flex;flex-direction:column;gap:11px;}
.crow{background:var(--surf);border:1px solid var(--brd);border-radius:10px;overflow:hidden;animation:fi .2s ease both;}
.crtop{padding:10px 14px 8px;font-size:.9rem;font-weight:600;border-bottom:1px solid var(--brd);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:5px;}
.ctmeta{display:flex;gap:10px;align-items:center;}
.sav{color:var(--grn);font-size:.73rem;font-weight:400;}
.cmeta{color:var(--dim);font-size:.65rem;}
.cells{display:flex;flex-wrap:wrap;}
.cell{flex:1;min-width:145px;padding:10px 14px;border-left:1px solid var(--brd);}
body.ltr .cell{border-left:none;border-right:1px solid var(--brd);}
.cell:last-child{border-left:none;}
body.ltr .cell:last-child{border-right:none;}
.cell.best{background:rgba(63,185,80,.07);}
.cch{font-size:.68rem;font-weight:700;margin-bottom:4px;}
.cpr{font-family:'Space Mono',monospace;font-size:1.3rem;font-weight:700;}
.cpr s{font-size:.7rem;color:var(--dim);font-weight:400;}
.cdiff{font-size:.68rem;margin-top:2px;}.cdiff.ch{color:var(--grn);}.cdiff.ex{color:var(--red);}
.nd{font-size:.75rem;color:var(--dim);margin-top:5px;opacity:.3;}

.empty{padding:60px 20px;text-align:center;color:var(--dim);line-height:2;}
#pg{padding:12px 20px 30px;display:flex;gap:6px;justify-content:center;flex-wrap:wrap;}
.pb{padding:5px 11px;background:var(--surf2);border:1px solid var(--brd);border-radius:6px;color:var(--dim);cursor:pointer;font-size:.79rem;transition:all .15s;}
.pb:hover{border-color:var(--acc);color:var(--txt);}
.pb.on{background:var(--acc);border-color:var(--acc);color:#0d1117;font-weight:700;}
</style>
</head>
<body>

<header>
  <div class="logo">price<b>compare</b></div>
  <div class="sw">
    <span class="qi">🔍</span>
    <input id="q" type="text" autofocus>
  </div>
  <div class="hs">
    <b id="cnt">0</b> <span data-t="results"></span> &nbsp;|&nbsp; __UPD__<br>
    __STATS__ <span data-t="products"></span> · __PRICES__ <span data-t="priceRecords"></span>
  </div>
  <!-- Переключатель языков -->
  <div class="lang-sw">
    <button class="lang-btn" data-lang="he">עב</button>
    <button class="lang-btn" data-lang="ru">Ру</button>
  </div>
</header>

<div id="chain-panel">
  <span class="lbl" data-t="myChains"></span>
  <span id="chain-btns" style="display:flex;flex-wrap:wrap;gap:6px;"></span>
  <button id="chain-all" data-t="selectAll"></button>
  <span class="chain-tip" id="chain-tip"></span>
</div>

<div class="bar">
  <span class="lbl" data-t="category"></span>
  <span class="chip on" data-q="">
    <span data-t="catAll"></span>
  </span>
  <span class="chip" data-q="מיץ">🧃 <span data-t="catJuice"></span></span>
  <span class="chip" data-q="חלב">🥛 <span data-t="catMilk"></span></span>
  <span class="chip" data-q="לחם">🍞 <span data-t="catBread"></span></span>
  <span class="chip" data-q="גבינה">🧀 <span data-t="catCheese"></span></span>
  <span class="chip" data-q="ביצים">🥚 <span data-t="catEggs"></span></span>
  <span class="chip" data-q="עוף">🍗 <span data-t="catChicken"></span></span>
  <span class="chip" data-q="אורז">🌾 <span data-t="catRice"></span></span>
  <span class="chip" data-q="מים">💧 <span data-t="catWater"></span></span>
  <span class="chip" data-q="קפה">☕ <span data-t="catCoffee"></span></span>
  <span class="chip" data-q="שמן">🫙 <span data-t="catOil"></span></span>
  <span class="chip" data-q="שוקולד">🍫 <span data-t="catChoc"></span></span>
  <div class="div"></div>
  <span class="lbl" data-t="sort"></span>
  <button class="sb on" data-s="multi" data-t="sortNetworks"></button>
  <button class="sb" data-s="save" data-t="sortSaving"></button>
  <button class="sb" data-s="asc" data-t="sortAsc"></button>
  <button class="sb" data-s="desc" data-t="sortDesc"></button>
  <div class="div"></div>
  <button class="vb on" id="bg" data-t="viewGrid"></button>
  <button class="vb" id="bc" data-t="viewCompare"></button>
</div>

<div id="res" class="gv"></div>
<div id="pg"></div>

<script>
const A   = __DATA__;
const C   = __COLORS__;
const CH  = __CHAINS__;
const PG  = 60;
const LS_CHAINS = "price_tracker_active_chains";
const LS_LANG   = "price_tracker_lang";

// ── Все строки интерфейса ─────────────────────────────────────────
const LANG = {
  he: {
    dir: "rtl", htmlLang: "he",
    searchPlaceholder: "חפש לפי שם... חלב, לחם, מיץ, ביצים",
    results: "תוצאות", products: "מוצרים", priceRecords: "מחירים בבסיס הנתונים",
    myChains: "הרשתות שלי:", selectAll: "בחר הכל",
    chainTipAll: "מציג את כל הרשתות",
    chainTipPartial: (n, total) => `מציג ${n} מתוך ${total} רשתות`,
    category: "קטגוריה:", sort: "מיון:",
    catAll: "הכל", catJuice: "מיץ", catMilk: "חלב", catBread: "לחם",
    catCheese: "גבינה", catEggs: "ביצים", catChicken: "עוף", catRice: "אורז",
    catWater: "מים", catCoffee: "קפה", catOil: "שמן", catChoc: "שוקולד",
    sortNetworks: "מס׳ רשתות ↓", sortSaving: "חיסכון ↓",
    sortAsc: "מחיר ↑", sortDesc: "מחיר ↓",
    viewGrid: "📦 כרטיסיות", viewCompare: "⚖️ השוואה",
    cheapest: "זול✓", saving: (n) => `💰 חיסכון עד ${n} ₪`,
    noData: "אין נתונים", noResults: "לא נמצאו תוצאות",
    networks: "רשתות", moreExpensive: (n) => `+${n} ₪ יותר יקר`, cheapestLabel: "הכי זול",
  },
  ru: {
    dir: "ltr", htmlLang: "ru",
    searchPlaceholder: "Поиск... молоко, хлеб, сок, яйца / חלב, לחם, מיץ",
    results: "результатов", products: "товаров", priceRecords: "записей цен в базе",
    myChains: "Мои магазины:", selectAll: "Выбрать все",
    chainTipAll: "Показаны все сети",
    chainTipPartial: (n, total) => `Показано ${n} из ${total} сетей`,
    category: "Категория:", sort: "Сортировка:",
    catAll: "Все", catJuice: "Сок", catMilk: "Молоко", catBread: "Хлеб",
    catCheese: "Сыр", catEggs: "Яйца", catChicken: "Курица", catRice: "Рис",
    catWater: "Вода", catCoffee: "Кофе", catOil: "Масло", catChoc: "Шоколад",
    sortNetworks: "По сетям ↓", sortSaving: "По экономии ↓",
    sortAsc: "Цена ↑", sortDesc: "Цена ↓",
    viewGrid: "📦 Карточки", viewCompare: "⚖️ Сравнение",
    cheapest: "Дёшево✓", saving: (n) => `💰 Экономия до ${n} ₪`,
    noData: "Нет данных", noResults: "Ничего не найдено",
    networks: "сетей", moreExpensive: (n) => `+${n} ₪ дороже`, cheapestLabel: "Дешевле всех",
  }
};

// ── Язык ──────────────────────────────────────────────────────────
function loadLang() {
  try { return localStorage.getItem(LS_LANG) || "he"; } catch(e) { return "he"; }
}
function saveLang(l) {
  try { localStorage.setItem(LS_LANG, l); } catch(e) {}
}

let lang = loadLang();

function applyLang() {
  const L = LANG[lang];
  const html = document.documentElement;
  const body = document.body;

  // Направление текста и язык документа
  html.setAttribute("dir", L.dir);
  html.setAttribute("lang", L.htmlLang);
  body.classList.toggle("ltr", lang === "ru");

  // Плейсхолдер поиска
  document.getElementById("q").placeholder = L.searchPlaceholder;

  // Все элементы с data-t
  document.querySelectorAll("[data-t]").forEach(el => {
    const key = el.dataset.t;
    if (typeof L[key] === "string") el.textContent = L[key];
  });

  // Кнопки языков
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.lang === lang);
  });

  // Обновляем подсказку про сети
  updateChainTip();
}

document.querySelectorAll(".lang-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    lang = btn.dataset.lang;
    saveLang(lang);
    applyLang();
    render(); // перерисовываем карточки с новыми строками
  });
});

// ── Выбор сетей ───────────────────────────────────────────────────
function loadActiveChains() {
  try {
    const saved = localStorage.getItem(LS_CHAINS);
    if (saved) {
      const arr = JSON.parse(saved);
      return new Set(arr.filter(ch => CH.includes(ch)));
    }
  } catch(e) {}
  return new Set(CH);
}
function saveActiveChains() {
  try { localStorage.setItem(LS_CHAINS, JSON.stringify([...activeChains])); } catch(e) {}
}

let activeChains = loadActiveChains();

function buildChainButtons() {
  const container = document.getElementById("chain-btns");
  container.innerHTML = "";
  CH.forEach(ch => {
    const color = C[ch] || "#8b949e";
    const count = A.filter(r => r.ch[ch]).length;
    const on = activeChains.has(ch);
    const btn = document.createElement("button");
    btn.className = "chain-btn" + (on ? " active" : "");
    btn.dataset.chain = ch;
    btn.style.borderColor = on ? color : "";
    btn.style.background  = on ? color + "22" : "";
    btn.style.color       = on ? color : "";
    btn.innerHTML = `<span class="chain-dot" style="background:${color}"></span>${ch}<span class="chain-count">${count.toLocaleString()}</span>`;
    btn.addEventListener("click", () => toggleChain(ch, btn, color));
    container.appendChild(btn);
  });
  updateChainTip();
}

function toggleChain(ch, btn, color) {
  if (activeChains.has(ch)) {
    if (activeChains.size <= 1) return;
    activeChains.delete(ch);
    btn.classList.remove("active");
    btn.style.borderColor = btn.style.background = btn.style.color = "";
  } else {
    activeChains.add(ch);
    btn.classList.add("active");
    btn.style.borderColor = color;
    btn.style.background  = color + "22";
    btn.style.color       = color;
  }
  saveActiveChains(); updateChainTip(); pg=1; render();
}

document.getElementById("chain-all").addEventListener("click", () => {
  activeChains = new Set(CH);
  saveActiveChains();
  buildChainButtons();
  pg=1; render();
});

function updateChainTip() {
  const L = LANG[lang];
  const tip = document.getElementById("chain-tip");
  tip.textContent = activeChains.size === CH.length
    ? L.chainTipAll
    : L.chainTipPartial(activeChains.size, CH.length);
}

// ── Фильтр и сортировка ───────────────────────────────────────────
let q="", srt="multi", pg=1, mode="grid";

const norm = s => (s||"").toLowerCase();
function activeCh(row) {
  const r={};
  for (const ch of activeChains) if (row.ch[ch]!==undefined) r[ch]=row.ch[ch];
  return r;
}
const vals  = ch => Object.values(ch);
const minP  = ch => Math.min(...vals(ch));
const maxP  = ch => Math.max(...vals(ch));
const saveV = ch => vals(ch).length<2 ? 0 : +(maxP(ch)-minP(ch)).toFixed(2);

function filt() {
  const ts = q.trim().split(/\s+/).filter(Boolean);
  return A.filter(r => {
    const ch = activeCh(r);
    if (!Object.keys(ch).length) return false;
    if (!ts.length) return true;
    return ts.every(t => norm(r.n).includes(norm(t)) || norm(r.m).includes(norm(t)));
  });
}
function doSort(arr) {
  if (srt==="save")  return [...arr].sort((a,b)=>saveV(activeCh(b))-saveV(activeCh(a)));
  if (srt==="asc")   return [...arr].sort((a,b)=>minP(activeCh(a))-minP(activeCh(b)));
  if (srt==="desc")  return [...arr].sort((a,b)=>minP(activeCh(b))-minP(activeCh(a)));
  return [...arr].sort((a,b)=>{
    const da=Object.keys(activeCh(a)).length, db=Object.keys(activeCh(b)).length;
    return db-da || minP(activeCh(a))-minP(activeCh(b));
  });
}

// ── Рендер ────────────────────────────────────────────────────────
function renderGrid(sl) {
  const L = LANG[lang];
  return sl.map((r,i)=>{
    const ch=activeCh(r), mp=minP(ch), sv=saveV(ch);
    const cells=Object.entries(ch).map(([chain,price])=>{
      const col=C[chain]||"#8b949e", best=price===mp;
      const prev = r.prev && r.prev[chain];
      const diff = (prev !== undefined && prev !== null)
        ? price - prev
        : null;
      const diffText=diff && Math.abs(diff)>0.01 ? (diff>0?`⬆ +${diff.toFixed(2)}`:` ⬇ ${diff.toFixed(2)}`) : "";
      return `<div class="price-cell${best?" best":""}">
        <div class="pc-chain" style="color:${col}">${best?"✓ ":""}${chain}</div>
        <div class="pc-price" style="color:${col}">${price} <span style="font-size:.7rem;color:var(--dim)">₪</span></div>
        ${diffText?`<div class="pc-diff${diff>0?" up":" down"}">${diffText} ₪</div>`:""}
        ${r.s?`<div class="pc-unit">${r.s}</div>`:""}
      </div>`;
    }).join("");
    return `<div class="card" style="animation-delay:${(i%24)*10}ms">
      <div class="cn">${r.n}</div>
      <div class="price-row">${cells}</div>
      ${sv>0.3?`<div class="saving">${L.saving(sv)}</div>`:""}
    </div>`;
  }).join("");
}

function renderCompare(sl) {
  const L = LANG[lang];
  const activeCHList = CH.filter(ch=>activeChains.has(ch));
  return sl.map((r,i)=>{
    const ch=activeCh(r), mp=minP(ch), sv=saveV(ch);
    const cells=activeCHList.map(chain=>{
      const col=C[chain]||"#8b949e";
      if (ch[chain]===undefined) return `<div class="cell">
        <div class="cch" style="color:${col}">${chain}</div>
        <div class="nd">${L.noData}</div>
      </div>`;
      const price=ch[chain], best=price===mp, diff=+(price-mp).toFixed(2);
      return `<div class="cell${best?" best":""}">
        <div class="cch" style="color:${col}">
          ${best?`<span style="background:var(--grn);color:#0d1117;padding:1px 6px;border-radius:8px;font-size:.62rem;margin-left:4px">${L.cheapest}</span>`:""}
          ${chain}
        </div>
        <div class="cpr" style="color:${col}">${price} <s>₪</s></div>
        ${r.s?`<div style="font-size:.65rem;color:var(--dim)">${r.s}</div>`:""}
        ${diff>0?`<div class="cdiff ex">${L.moreExpensive(diff)}</div>`:`<div class="cdiff ch">${L.cheapestLabel}</div>`}
      </div>`;
    }).join("");
    return `<div class="crow" style="animation-delay:${(i%20)*12}ms">
      <div class="crtop">
        <span>${r.n}</span>
        <span class="ctmeta">
          ${sv>0.3?`<span class="sav">${L.saving(sv)}</span>`:""}
          <span class="cmeta">${Object.keys(ch).length}/${activeCHList.length} ${L.networks} · ${r.c}</span>
        </span>
      </div>
      <div class="cells">${cells}</div>
    </div>`;
  }).join("");
}

function render() {
  const L=LANG[lang];
  const f=filt(), s=doSort(f), total=s.length;
  const sl=s.slice((pg-1)*PG, pg*PG);
  document.getElementById("cnt").textContent=total.toLocaleString();
  document.getElementById("res").innerHTML=sl.length
    ?(mode==="compare"?renderCompare(sl):renderGrid(sl))
    :`<div class="empty">${L.noResults}</div>`;
  const pages=Math.ceil(total/PG);
  const p=document.getElementById("pg");
  if(pages<=1){p.innerHTML="";return;}
  let b="";
  if(pg>1) b+=`<button class="pb" onclick="go(${pg-1})">‹</button>`;
  for(let i=1;i<=pages;i++){
    if(i===1||i===pages||Math.abs(i-pg)<=2)
      b+=`<button class="pb${i===pg?" on":""}" onclick="go(${i})">${i}</button>`;
    else if(Math.abs(i-pg)===3) b+=`<span style="color:var(--dim)">…</span>`;
  }
  if(pg<pages) b+=`<button class="pb" onclick="go(${pg+1})">›</button>`;
  p.innerHTML=b;
}
function go(n){pg=n;render();window.scrollTo(0,0);}

// ── Слушатели ─────────────────────────────────────────────────────
let db;
document.getElementById("q").addEventListener("input",e=>{
  clearTimeout(db);
  db=setTimeout(()=>{
    q=e.target.value;pg=1;
    document.querySelectorAll(".chip").forEach(c=>c.classList.remove("on"));
    document.querySelector('.chip[data-q=""]').classList.add("on");
    render();
  },200);
});
document.querySelector(".bar").addEventListener("click",e=>{
  const c=e.target.closest(".chip");
  if(c){
    document.querySelectorAll(".chip").forEach(x=>x.classList.remove("on"));
    c.classList.add("on");q=c.dataset.q;pg=1;
    document.getElementById("q").value=q;render();return;
  }
  const s=e.target.closest(".sb");
  if(s){
    document.querySelectorAll(".sb").forEach(x=>x.classList.remove("on"));
    s.classList.add("on");srt=s.dataset.s;pg=1;render();return;
  }
});
document.getElementById("bg").addEventListener("click",()=>{
  mode="grid";document.getElementById("res").className="gv";
  document.getElementById("bg").classList.add("on");
  document.getElementById("bc").classList.remove("on");pg=1;render();
});
document.getElementById("bc").addEventListener("click",()=>{
  mode="compare";document.getElementById("res").className="cv";
  document.getElementById("bc").classList.add("on");
  document.getElementById("bg").classList.remove("on");pg=1;render();
});

// ── Инициализация ─────────────────────────────────────────────────
buildChainButtons();
applyLang();   // применяем язык (включая строки кнопок через data-t)
render();
</script>
</body>
</html>"""

html = (
    html.replace("__UPD__", UPD)
    .replace("__STATS__", str(stats["products"]))
    .replace("__PRICES__", str(stats["prices"]))
    .replace("__DATA__", D)
    .replace("__COLORS__", C)
    .replace("__CHAINS__", CH)
)

with open("price_viewer.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✓ Создан price_viewer.html с поддержкой иврита и русского языка")
print(f"  Товаров: {len(catalog):,} | В 2+ сетях: {in_multiple:,}")
