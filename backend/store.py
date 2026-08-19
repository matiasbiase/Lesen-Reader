"""
Vocabulary storage, in SQLite.

The state model comes from Lute: every word carries a status that follows you
across every text. Here there are 3 of them (nueva / aprendiendo / sabida) plus
plain spaced review, so the word folder isn't just a dead list.

⚠️ Those three status values are stored strings, not labels: they're written to
the database and read by `web/app.js`. Renaming them is a migration.
"""
import json
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "lesen.db"

# Review intervals in days. A hit moves up a step, a miss goes back to the
# start. It's Leitner, not SM-2: enough, and you can explain it in one line.
STEPS = [0, 1, 3, 7, 16, 35, 90]
DAY = 86400


def conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS words (
            lemma       TEXT PRIMARY KEY,
            form        TEXT,
            pos         TEXT,
            article     TEXT,
            es          TEXT,
            sense_n     TEXT,
            sense_de    TEXT,
            separable   TEXT,
            sentence    TEXT,
            src_title   TEXT,
            src_url     TEXT,
            example_de  TEXT,
            example_es  TEXT,
            status      TEXT DEFAULT 'aprendiendo',
            box         INTEGER DEFAULT 0,
            due         REAL DEFAULT 0,
            hits        INTEGER DEFAULT 0,
            misses      INTEGER DEFAULT 0,
            created     REAL,
            reviewed    REAL
        );
        CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
        -- Se guarda el texto ya extraído, no solo el link: así volver a una
        -- nota es instantáneo y sigue estando aunque el diario la baje.
        CREATE TABLE IF NOT EXISTS saved (
            url    TEXT PRIMARY KEY,
            title  TEXT,
            source TEXT,
            topic  TEXT,
            text   TEXT,
            tenses TEXT,
            saved  REAL,
            read   REAL
        );
        CREATE INDEX IF NOT EXISTS idx_status ON words(status);
        CREATE INDEX IF NOT EXISTS idx_due ON words(due);
        """)


def save_word(d: dict) -> dict:
    now = time.time()
    sep = json.dumps(d.get("separable")) if d.get("separable") else None
    with conn() as c:
        cur = c.execute("SELECT lemma, box FROM words WHERE lemma=?", (d["lemma"],))
        exists = cur.fetchone()
        if exists:
            c.execute("""UPDATE words SET form=?, es=COALESCE(NULLIF(?,''),es),
                         sentence=?, src_title=?, src_url=?, status=? WHERE lemma=?""",
                      (d.get("form"), d.get("es", ""), d.get("sentence"), d.get("src_title"),
                       d.get("src_url"), d.get("status", "aprendiendo"), d["lemma"]))
        else:
            c.execute("""INSERT INTO words (lemma, form, pos, article, es, sense_n, sense_de,
                         separable, sentence, src_title, src_url, example_de, example_es,
                         status, box, due, created)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
                      (d["lemma"], d.get("form"), d.get("pos"), d.get("article"),
                       d.get("es", ""), d.get("sense_n"), d.get("sense_de"), sep,
                       d.get("sentence"), d.get("src_title"), d.get("src_url"),
                       d.get("example_de"), d.get("example_es"),
                       d.get("status", "aprendiendo"), now, now))
    return get_word(d["lemma"])


def get_word(lemma: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM words WHERE lemma=?", (lemma,)).fetchone()
    return dict(r) if r else None


def list_words(status: str | None = None) -> list[dict]:
    q = "SELECT * FROM words"
    args = ()
    if status and status != "todas":
        q += " WHERE status=?"
        args = (status,)
    q += " ORDER BY created DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def statuses() -> dict[str, str]:
    """Map of lemma -> status, to paint a whole article in one pass."""
    with conn() as c:
        return {r["lemma"]: r["status"] for r in c.execute("SELECT lemma, status FROM words")}


def set_status(lemma: str, status: str):
    with conn() as c:
        c.execute("UPDATE words SET status=? WHERE lemma=?", (status, lemma))
    return get_word(lemma)


def delete_word(lemma: str):
    with conn() as c:
        c.execute("DELETE FROM words WHERE lemma=?", (lemma,))


def due_words(limit: int = 20) -> list[dict]:
    now = time.time()
    with conn() as c:
        rows = c.execute("""SELECT * FROM words WHERE status!='sabida' AND due<=?
                            ORDER BY due ASC LIMIT ?""", (now, limit)).fetchall()
    return [dict(r) for r in rows]


def review(lemma: str, ok: bool) -> dict:
    w = get_word(lemma)
    if not w:
        return {}
    box = w["box"] or 0
    box = min(box + 1, len(STEPS) - 1) if ok else 0
    status = "sabida" if ok and box >= len(STEPS) - 1 else "aprendiendo"
    with conn() as c:
        c.execute("""UPDATE words SET box=?, due=?, status=?, hits=hits+?, misses=misses+?,
                     reviewed=? WHERE lemma=?""",
                  (box, time.time() + STEPS[box] * DAY, status,
                   1 if ok else 0, 0 if ok else 1, time.time(), lemma))
    return get_word(lemma)


def save_article(d: dict) -> dict:
    with conn() as c:
        c.execute("""INSERT INTO saved (url,title,source,topic,text,tenses,saved)
                     VALUES (?,?,?,?,?,?,?)
                     ON CONFLICT(url) DO UPDATE SET title=excluded.title,
                     text=excluded.text, tenses=excluded.tenses""",
                  (d["url"], d.get("title"), d.get("source"), d.get("topic"),
                   d.get("text"), json.dumps(d.get("tenses", [])), time.time()))
    return get_article(d["url"])


def get_article(url: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM saved WHERE url=?", (url,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["tenses"] = json.loads(d["tenses"] or "[]")
    return d


def list_articles() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT url,title,source,topic,tenses,saved,read "
                         "FROM saved ORDER BY saved DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tenses"] = json.loads(d["tenses"] or "[]")
        out.append(d)
    return out


def unsave_article(url: str):
    with conn() as c:
        c.execute("DELETE FROM saved WHERE url=?", (url,))


def mark_read(url: str):
    with conn() as c:
        c.execute("UPDATE saved SET read=? WHERE url=?", (time.time(), url))


def get_setting(k: str, default=None):
    with conn() as c:
        r = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def set_setting(k: str, v):
    with conn() as c:
        c.execute("INSERT INTO settings (k,v) VALUES (?,?) "
                  "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))


def stats() -> dict:
    with conn() as c:
        row = c.execute("""SELECT COUNT(*) n,
                           SUM(status='aprendiendo') aprendiendo,
                           SUM(status='sabida') sabidas FROM words""").fetchone()
        due = c.execute("SELECT COUNT(*) n FROM words WHERE status!='sabida' AND due<=?",
                        (time.time(),)).fetchone()["n"]
    return {"total": row["n"] or 0, "aprendiendo": row["aprendiendo"] or 0,
            "sabidas": row["sabidas"] or 0, "para_repasar": due}
