import io
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
from xml.sax.saxutils import escape as xesc

import feedparser
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from typing import Optional

from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
DB = DATA / "search.db"
HEADERS = {"User-Agent": "NEWS-SEARCH/1.0 (local app)"}
PERIODS = {"1h", "1d", "7d", "30d", "1y"}
CATS = {"Regional", "Nasional", "Internasional", "Negatif TNI"}

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

with conn() as c:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS saved(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, source TEXT DEFAULT '',
        url TEXT NOT NULL UNIQUE, published_at TEXT DEFAULT '', query TEXT DEFAULT '', saved_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS queries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, query TEXT NOT NULL,
        period TEXT DEFAULT '', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL UNIQUE, last_used TEXT NOT NULL, hits INTEGER DEFAULT 1);
    """)
    cols = {r[1] for r in c.execute("PRAGMA table_info(saved)").fetchall()}
    for col in ("category", "region"):
        if col not in cols:
            c.execute(f"ALTER TABLE saved ADD COLUMN {col} TEXT DEFAULT ''")
    for table in ("saved", "queries"):
        tcols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if "pinned" not in tcols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN pinned INTEGER DEFAULT 0")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS lists(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, pinned INTEGER DEFAULT 0, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS list_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, list_id INTEGER NOT NULL, title TEXT NOT NULL, source TEXT DEFAULT '',
        url TEXT NOT NULL, published_at TEXT DEFAULT '', added_at TEXT NOT NULL, UNIQUE(list_id, url));
    """)

app = FastAPI(title="NEWS SEARCH", version="1.6.0")

def now():
    return datetime.now(timezone.utc).isoformat()

def build_url(q: str, when: str) -> tuple[str, str]:
    query = q.strip()
    if when in PERIODS and "when:" not in query:
        query += f" when:{when}"
    return query, "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=id&gl=ID&ceid=ID:id"

def parse_items(content: bytes) -> list[dict]:
    items = []
    for e in feedparser.parse(content).entries[:100]:
        title = (e.get("title") or "").strip()
        url = (e.get("link") or "").strip()
        if not title or not url:
            continue
        src = ((e.get("source") or {}).get("title") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        published = ""
        try:
            dt = parsedate_to_datetime(e.get("published", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            published = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
        items.append({"title": title, "source": src, "url": url, "published_at": published})
    return items

@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=300), when: str = "", save: bool = True, track: bool = True,
           cat: str = "", region: str = ""):
    query, url = build_url(q, when)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Gagal menghubungi Google News: {exc}")
    items = parse_items(r.content)
    if track:  # hanya pencarian manual yang masuk riwayat; berita TIDAK disimpan otomatis
        with conn() as c:
            c.execute("""INSERT INTO history(query,last_used) VALUES(?,?)
                         ON CONFLICT(query) DO UPDATE SET last_used=excluded.last_used, hits=hits+1""", (query, now()))
    return {"query": query, "count": len(items), "items": items}

@app.get("/api/saved")
def saved(q: str = "", limit: int = Query(500, ge=1, le=2000)):
    sql, args = "SELECT * FROM saved WHERE 1=1", []
    if q:
        sql += " AND (title LIKE ? OR source LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY pinned DESC, COALESCE(NULLIF(published_at,''), saved_at) DESC LIMIT ?"
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args + [limit]).fetchall()]

@app.delete("/api/saved")
def clear_saved():
    with conn() as c:
        n = c.execute("DELETE FROM saved").rowcount
    return {"deleted": n}

@app.delete("/api/saved/{item_id}")
def delete_saved(item_id: int):
    with conn() as c:
        if not c.execute("DELETE FROM saved WHERE id=?", (item_id,)).rowcount:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return {"ok": True}

@app.get("/api/history")
def history():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM history ORDER BY last_used DESC LIMIT 50").fetchall()]

@app.delete("/api/history")
def clear_history():
    with conn() as c:
        c.execute("DELETE FROM history")
    return {"ok": True}

class QueryIn(BaseModel):
    name: str = ""
    query: str
    period: str = ""

@app.get("/api/queries")
def list_queries():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM queries ORDER BY pinned DESC, id DESC").fetchall()]

@app.post("/api/queries")
def add_query(p: QueryIn):
    query = p.query.strip()
    if not query or len(query) > 300:
        raise HTTPException(status_code=400, detail="Kueri kosong atau lebih dari 300 karakter")
    period = p.period if p.period in PERIODS else ""
    with conn() as c:
        row = c.execute("SELECT id FROM queries WHERE query=? AND period=?", (query, period)).fetchone()
        if row:
            return {"id": row["id"], "exists": True}
        cur = c.execute("INSERT INTO queries(name,query,period,created_at) VALUES(?,?,?,?)",
                        ((p.name.strip() or query)[:80], query, period, now()))
    return {"id": cur.lastrowid, "exists": False}

@app.delete("/api/queries")
def clear_queries():
    with conn() as c:
        n = c.execute("DELETE FROM queries").rowcount
    return {"deleted": n}

@app.delete("/api/queries/{query_id}")
def delete_query(query_id: int):
    with conn() as c:
        if not c.execute("DELETE FROM queries WHERE id=?", (query_id,)).rowcount:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return {"ok": True}

class QueryEdit(BaseModel):
    name: Optional[str] = None
    query: Optional[str] = None
    period: Optional[str] = None

@app.patch("/api/queries/{query_id}")
def edit_query(query_id: int, p: QueryEdit):
    with conn() as c:
        row = c.execute("SELECT * FROM queries WHERE id=?", (query_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
        query = (p.query if p.query is not None else row["query"]).strip()
        if not query or len(query) > 300:
            raise HTTPException(status_code=400, detail="Teks pencarian kosong atau lebih dari 300 karakter")
        name = (p.name if p.name is not None else row["name"]).strip() or query
        period = row["period"] if p.period is None else (p.period if p.period in PERIODS else "")
        c.execute("UPDATE queries SET name=?, query=?, period=? WHERE id=?", (name[:80], query, period, query_id))
    return {"ok": True}

class NewsEdit(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    region: Optional[str] = None

@app.patch("/api/saved/{item_id}")
def edit_saved(item_id: int, p: NewsEdit):
    with conn() as c:
        row = c.execute("SELECT * FROM saved WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
        title = (p.title if p.title is not None else row["title"]).strip()
        if not title:
            raise HTTPException(status_code=400, detail="Judul tidak boleh kosong")
        category = row["category"] if p.category is None else (p.category if p.category in CATS else "")
        region = row["region"] if p.region is None else p.region.strip()[:40]
        c.execute("UPDATE saved SET title=?, category=?, region=? WHERE id=?", (title[:500], category, region, item_id))
    return {"ok": True}

class HistEdit(BaseModel):
    query: str

@app.patch("/api/history/{item_id}")
def edit_history(item_id: int, p: HistEdit):
    query = p.query.strip()
    if not query or len(query) > 300:
        raise HTTPException(status_code=400, detail="Teks pencarian kosong atau lebih dari 300 karakter")
    try:
        with conn() as c:
            if not c.execute("UPDATE history SET query=? WHERE id=?", (query, item_id)).rowcount:
                raise HTTPException(status_code=404, detail="Tidak ditemukan")
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Teks pencarian itu sudah ada di riwayat")
    return {"ok": True}

@app.delete("/api/history/{item_id}")
def delete_history(item_id: int):
    with conn() as c:
        if not c.execute("DELETE FROM history WHERE id=?", (item_id,)).rowcount:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return {"ok": True}


# ---------- Arsip Berita (hanya berita yang dipilih pengguna) ----------
class SaveItem(BaseModel):
    title: str = ""
    url: str = ""
    source: str = ""
    published_at: str = ""
    query: str = ""
    category: str = ""
    region: str = ""

class SaveIn(BaseModel):
    items: list[SaveItem]
    pinned: int = 0

class IdsIn(BaseModel):
    ids: list[int]
    pinned: int = 1

@app.post("/api/saved")
def save_items(p: SaveIn):
    added = 0
    with conn() as c:
        for i in p.items[:500]:
            if not i.url or not i.title:
                continue
            cat = i.category if i.category in CATS else ""
            cur = c.execute(
                "INSERT OR IGNORE INTO saved(title,source,url,published_at,query,saved_at,category,region,pinned) VALUES(?,?,?,?,?,?,?,?,?)",
                (i.title[:500], i.source[:120], i.url, i.published_at, i.query[:300], now(), cat, i.region[:40], 1 if p.pinned else 0))
            if cur.rowcount:
                added += 1
            elif p.pinned:
                c.execute("UPDATE saved SET pinned=1 WHERE url=?", (i.url,))
            if cat:
                c.execute("UPDATE saved SET category=?, region=? WHERE url=? AND COALESCE(category,'')=''", (cat, i.region[:40], i.url))
    return {"added": added, "total": len(p.items)}

@app.post("/api/saved/pin")
def pin_saved(p: IdsIn):
    with conn() as c:
        c.executemany("UPDATE saved SET pinned=? WHERE id=?", [(1 if p.pinned else 0, i) for i in p.ids])
    return {"ok": True}

@app.post("/api/saved/remove")
def remove_saved(p: IdsIn):
    with conn() as c:
        c.executemany("DELETE FROM saved WHERE id=?", [(i,) for i in p.ids])
    return {"ok": True, "deleted": len(p.ids)}

@app.post("/api/queries/{query_id}/pin")
def pin_query(query_id: int):
    with conn() as c:
        if not c.execute("UPDATE queries SET pinned=1-COALESCE(pinned,0) WHERE id=?", (query_id,)).rowcount:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return {"ok": True}

# ---------- Daftar Simpan ----------
class ListIn(BaseModel):
    name: str

class ListItemsIn(BaseModel):
    items: list[SaveItem]

class UrlsIn(BaseModel):
    urls: list[str]

@app.get("/api/lists")
def get_lists():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT l.*, (SELECT COUNT(*) FROM list_items i WHERE i.list_id=l.id) AS n FROM lists l ORDER BY l.pinned DESC, l.id DESC").fetchall()]

@app.post("/api/lists")
def create_list(p: ListIn):
    name = p.name.strip()[:80]
    if not name:
        raise HTTPException(status_code=400, detail="Nama daftar tidak boleh kosong")
    with conn() as c:
        row = c.execute("SELECT id FROM lists WHERE name=?", (name,)).fetchone()
        if row:
            return {"id": row["id"], "exists": True}
        cur = c.execute("INSERT INTO lists(name,created_at) VALUES(?,?)", (name, now()))
    return {"id": cur.lastrowid, "exists": False}

@app.patch("/api/lists/{list_id}")
def rename_list(list_id: int, p: ListIn):
    name = p.name.strip()[:80]
    if not name:
        raise HTTPException(status_code=400, detail="Nama daftar tidak boleh kosong")
    with conn() as c:
        if not c.execute("UPDATE lists SET name=? WHERE id=?", (name, list_id)).rowcount:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return {"ok": True}

@app.post("/api/lists/{list_id}/pin")
def pin_list(list_id: int):
    with conn() as c:
        if not c.execute("UPDATE lists SET pinned=1-COALESCE(pinned,0) WHERE id=?", (list_id,)).rowcount:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return {"ok": True}

@app.delete("/api/lists/{list_id}")
def delete_list(list_id: int):
    with conn() as c:
        c.execute("DELETE FROM list_items WHERE list_id=?", (list_id,))
        if not c.execute("DELETE FROM lists WHERE id=?", (list_id,)).rowcount:
            raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return {"ok": True}

@app.get("/api/lists/{list_id}/items")
def list_items(list_id: int):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM list_items WHERE list_id=? ORDER BY COALESCE(NULLIF(published_at,''), added_at) DESC", (list_id,)).fetchall()]

@app.post("/api/lists/{list_id}/items")
def add_list_items(list_id: int, p: ListItemsIn):
    added = 0
    with conn() as c:
        if not c.execute("SELECT 1 FROM lists WHERE id=?", (list_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Daftar tidak ditemukan")
        for i in p.items[:500]:
            if not i.url or not i.title:
                continue
            cur = c.execute("INSERT OR IGNORE INTO list_items(list_id,title,source,url,published_at,added_at) VALUES(?,?,?,?,?,?)",
                            (list_id, i.title[:500], i.source[:120], i.url, i.published_at, now()))
            added += cur.rowcount
    return {"added": added, "total": len(p.items)}

@app.post("/api/lists/{list_id}/remove")
def remove_list_items(list_id: int, p: UrlsIn):
    with conn() as c:
        c.executemany("DELETE FROM list_items WHERE list_id=? AND url=?", [(list_id, u) for u in p.urls])
    return {"ok": True}

# ---------- Ekspor Word (.docx) tanpa library tambahan ----------
MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

def _x(text) -> str:
    return xesc(_BAD.sub("", str(text or "")), {'"': "&quot;"})

def _fmt_dt(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone()  # zona waktu komputer
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}, {dt:%H.%M}"

def _utc_label() -> str:
    off = datetime.now().astimezone().utcoffset()
    mins = int(off.total_seconds() // 60) if off else 0
    sign = "+" if mins >= 0 else "-"
    h, m = divmod(abs(mins), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")

def _run(text, bold=False, size=21, color=None, underline=False):
    rpr = '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>' + ("<w:b/>" if bold else "")
    rpr += (f'<w:color w:val="{color}"/>' if color else "") + f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    rpr += '<w:u w:val="single"/>' if underline else ""
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{_x(text)}</w:t></w:r>'

def _para(runs, align=None, after=0):
    ppr = f'<w:spacing w:before="0" w:after="{after}"/>' + (f'<w:jc w:val="{align}"/>' if align else "")
    return f"<w:p><w:pPr>{ppr}</w:pPr>{runs}</w:p>"

def _cell(width, content, fill=None):
    shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
    return f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shd}</w:tcPr>{content}</w:tc>'

def build_docx(title: str, items) -> bytes:
    widths = [700, 5100, 5700, 3338]
    rels = []
    heads = ["No", "Judul Berita", "Link", f"Tanggal & Jam Terbit ({_utc_label()})"]
    aligns = ["center", None, None, None]
    head = "".join(_cell(w, _para(_run(t, bold=True, color="FFFFFF"), align=al), fill="1F3864")
                   for w, t, al in zip(widths, heads, aligns))
    rows = [f"<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>{head}</w:tr>"]
    for n, it in enumerate(items, 1):
        fill = "EEF3FB" if n % 2 == 0 else None
        tp = _para(_run(it.title or "(tanpa judul)", bold=True, size=22), after=40 if it.source else 0)
        if it.source:
            tp += _para(_run(it.source, size=18, color="6B7280"))
        url = (it.url or "").strip()
        if url:
            rid = f"rId{len(rels) + 10}"
            rels.append((rid, url))
            lp = _para(f'<w:hyperlink r:id="{rid}" w:history="1">{_run(url, size=17, color="0563C1", underline=True)}</w:hyperlink>')
        else:
            lp = _para(_run("-", size=18))
        rows.append("<w:tr><w:trPr><w:cantSplit/></w:trPr>"
                    + _cell(widths[0], _para(_run(str(n)), align="center"), fill)
                    + _cell(widths[1], tp, fill) + _cell(widths[2], lp, fill)
                    + _cell(widths[3], _para(_run(_fmt_dt(it.published_at))), fill) + "</w:tr>")
    border = lambda tag: f'<w:{tag} w:val="single" w:sz="4" w:space="0" w:color="8EA0B8"/>'
    tbl = ('<w:tbl><w:tblPr><w:tblW w:w="14838" w:type="dxa"/><w:tblBorders>'
           + "".join(border(t) for t in ("top", "left", "bottom", "right", "insideH", "insideV"))
           + '</w:tblBorders><w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
           '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'
           + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>" + "".join(rows) + "</w:tbl>")
    stamp = datetime.now().astimezone()
    body = (_para(_run(title, bold=True, size=36, color="1F3864"), after=80)
            + _para(_run(f"Dibuat: {stamp.day} {MONTHS[stamp.month - 1]} {stamp.year}, {stamp:%H.%M}  |  Jumlah berita: {len(items)}", size=20, color="6B7280"), after=200)
            + tbl + "<w:p/>"
            + '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
              '<w:pgMar w:top="1000" w:right="1000" w:bottom="1000" w:left="1000" w:header="500" w:footer="500" w:gutter="0"/></w:sectPr>')
    head_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    document = (head_xml + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>' + body + "</w:body></w:document>")
    doc_rels = (head_xml + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                          f'Target="{_x(u)}" TargetMode="External"/>' for rid, u in rels) + "</Relationships>")
    content_types = (head_xml + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    root_rels = (head_xml + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
    return buf.getvalue()

class ExportIn(BaseModel):
    title: str = "Daftar Berita Terpilih"
    items: list[SaveItem]

@app.post("/api/export/docx")
def export_docx(p: ExportIn):
    if not p.items:
        raise HTTPException(status_code=400, detail="Tidak ada berita yang dipilih")
    if len(p.items) > 1000:
        raise HTTPException(status_code=400, detail="Maksimal 1000 berita per file")
    data = build_docx((p.title or "Daftar Berita Terpilih").strip()[:120], p.items)
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": "attachment; filename=daftar_berita.docx"})

app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
