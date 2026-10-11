"""Local persistence. Transcripts are opt-in; credentials never enter SQLite."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .config import Settings

class Store:
    @classmethod
    def open_recover(cls, path):
        try:
            result = cls(path)
            with result.connection() as db:
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("Corrupt database")
            return result
        except sqlite3.DatabaseError as exc:
            # Never treat a locked/permission-denied database as corruption.
            code = getattr(exc, "sqlite_errorcode", None)
            if code not in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB) and str(exc) != "Corrupt database":
                raise
            import logging
            stamp = str(time.time_ns())
            for suffix in ("", "-wal", "-shm"):
                source = Path(str(path) + suffix)
                if source.exists():
                    source.rename(Path(str(path) + ".recovered-" + stamp + suffix))
            logging.getLogger("jarvis").warning("Corrupt SQLite state preserved in private recovery files; created a new database with microphone off.")
            return cls(path)

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                PRAGMA secure_delete=ON;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, title TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, conversation TEXT, role TEXT, content TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, content TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, label TEXT, tool TEXT, arguments TEXT);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA secure_delete=ON")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def settings(self) -> Settings:
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key='config'").fetchone()
        if not row:
            return Settings()
        try:
            data = json.loads(row[0])
            result = Settings(**{k: v for k, v in data.items() if k in Settings.__dataclass_fields__})
            result.validate()
            return result
        except (ValueError, TypeError, AttributeError, OSError):
            import logging
            logging.getLogger("jarvis").warning("Invalid saved preferences preserved; using safe defaults with microphone off. Save Settings to replace them.")
            return Settings()

    def save_settings(self, settings: Settings):
        settings.validate()
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('config', ?)", (json.dumps(settings.to_dict()),))

    def new_conversation(self, title="New conversation"):
        cid = uuid.uuid4().hex
        with self.connection() as db:
            db.execute("INSERT INTO conversations VALUES(?,?,?)", (cid, title[:100], time.time()))
        return cid

    def append(self, cid, role, content):
        if role not in {"user", "assistant"}:
            raise ValueError("Only conversation text is persisted.")
        with self.connection() as db:
            db.execute("INSERT INTO messages(conversation,role,content,created) VALUES(?,?,?,?)", (cid, role, content, time.time()))
            if role == "user":
                db.execute("UPDATE conversations SET title=? WHERE id=? AND title='New conversation'", (content[:70], cid))

    def conversations(self):
        with self.connection() as db:
            return db.execute("SELECT id,title FROM conversations ORDER BY created DESC LIMIT 100").fetchall()

    def messages(self, cid):
        with self.connection() as db:
            return [{"role": r, "content": c} for r,c in db.execute("SELECT role,content FROM messages WHERE conversation=? ORDER BY id", (cid,))]

    def delete_conversation(self, cid):
        with self.connection() as db:
            db.execute("DELETE FROM messages WHERE conversation=?", (cid,))
            db.execute("DELETE FROM conversations WHERE id=?", (cid,))
        self.compact()

    def prune(self, days):
        with self.connection() as db:
            cutoff = time.time() - days * 86400
            db.execute("DELETE FROM messages WHERE created<?", (cutoff,))
            db.execute("DELETE FROM conversations WHERE id NOT IN (SELECT conversation FROM messages)")
        self.compact()

    def memories(self):
        with self.connection() as db:
            return db.execute("SELECT id,content FROM memories ORDER BY created").fetchall()

    def save_memory(self, text):
        if not text.strip() or len(text) > 2000:
            raise ValueError("Memories must contain 1–2000 characters.")
        with self.connection() as db:
            count = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            if count >= 100:
                raise ValueError("Delete an old memory before adding more (limit 100).")
            db.execute("INSERT INTO memories VALUES(?,?,?)", (uuid.uuid4().hex, text.strip(), time.time()))

    def delete_memory(self, mid):
        with self.connection() as db:
            db.execute("DELETE FROM memories WHERE id=?", (mid,))
        self.compact()

    def commands(self):
        with self.connection() as db:
            return db.execute("SELECT id,label,tool,arguments FROM commands ORDER BY label").fetchall()

    def save_command(self, label, tool, arguments):
        with self.connection() as db:
            db.execute("INSERT INTO commands VALUES(?,?,?,?)", (uuid.uuid4().hex, label[:80], tool, json.dumps(arguments)))

    def delete_command(self, cid):
        with self.connection() as db:
            db.execute("DELETE FROM commands WHERE id=?", (cid,))

    def clear(self):
        with self.connection() as db:
            for table in ("messages", "conversations", "memories", "settings", "commands"):
                db.execute(f"DELETE FROM {table}")
        self.compact()

    def compact(self):
        with self.connection() as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("VACUUM")
