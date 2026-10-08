"""SQLite 保存唯一正文、元数据、父子区间与索引状态。"""
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, title TEXT, category TEXT, source_url TEXT,
                source_path TEXT, collected_at TEXT, version TEXT, body TEXT, metadata TEXT);
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY, doc_id TEXT REFERENCES documents(id), parent_id TEXT,
                section TEXT, start INTEGER, end INTEGER, text TEXT, kind TEXT);
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
            ''')
            db.execute("INSERT OR IGNORE INTO state VALUES ('index', ?)",
                       (json.dumps({'status': 'missing', 'message': '尚未建立索引'}),))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def state(self):
        with self.connect() as db:
            return json.loads(db.execute("SELECT value FROM state WHERE key='index'").fetchone()[0])

    def set_state(self, state):
        with self.connect() as db:
            db.execute("UPDATE state SET value=? WHERE key='index'", (json.dumps(state, ensure_ascii=False),))

    def bind_product(self, product_id):
        """持久化目录只属于一个产品，错误复用目录时停止，避免混查。"""
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key='product'").fetchone()
            if row and row[0] != product_id:
                raise ValueError('DATA_DIR 已属于其他产品，请为当前产品设置新的数据目录')
            if not row and db.execute('SELECT COUNT(*) FROM documents').fetchone()[0]:
                raise ValueError('旧数据目录没有产品标识，请使用新的 DATA_DIR；旧资料不会被删除')
            db.execute("INSERT OR IGNORE INTO state VALUES ('product', ?)", (product_id,))

    def save_document(self, doc):
        with self.connect() as db:
            self._save(db, doc)
            self._mark_stale(db)

    @staticmethod
    def _save(db, doc):
        db.execute('''INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET title=excluded.title, category=excluded.category,
                       source_url=excluded.source_url, source_path=excluded.source_path,
                       collected_at=excluded.collected_at, version=excluded.version,
                       body=excluded.body, metadata=excluded.metadata''',
                       tuple(doc[k] for k in ['id', 'title', 'category', 'source_url', 'source_path',
                                             'collected_at', 'version', 'body']) +
                       (json.dumps(doc['metadata'], ensure_ascii=False),))

    @staticmethod
    def _mark_stale(db):
        db.execute("UPDATE state SET value=? WHERE key='index'",
                   (json.dumps({'status': 'stale', 'message': '资料已变化，请重建索引'}, ensure_ascii=False),))

    def replace_snapshot(self, documents, product_id):
        """一次事务更新快照；移除清单中已删的快照文档，保留用户上传。"""
        ids = {d['id'] for d in documents}
        with self.connect() as db:
            db.execute('DELETE FROM chunks')  # 旧关系已失效，旧向量由下次成功重建清理。
            for row in db.execute('SELECT id, metadata FROM documents').fetchall():
                meta = json.loads(row['metadata'])
                if meta.get('snapshot_product') == product_id and row['id'] not in ids:
                    db.execute('DELETE FROM documents WHERE id=?', (row['id'],))
            for doc in documents:
                self._save(db, doc)
            self._mark_stale(db)

    def documents(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM documents ORDER BY title')]

    def document(self, doc_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
            return dict(row) if row else None

    def chunks(self, kind):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM chunks WHERE kind=? ORDER BY rowid', (kind,))]

    def replace_index(self, parents, children, state):
        with self.connect() as db:
            db.execute('DELETE FROM chunks')
            for kind, chunks in [('parent', parents), ('child', children)]:
                db.executemany('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)',
                               [tuple(asdict(c).values()) + (kind,) for c in chunks])
            db.execute("UPDATE state SET value=? WHERE key='index'", (json.dumps(state),))
