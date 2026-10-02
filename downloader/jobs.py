from datetime import datetime, timezone
import json
from contextlib import contextmanager
import sqlite3
import uuid


class Jobs:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, started TEXT, ended TEXT, status TEXT, source TEXT, parameters TEXT, result TEXT)')
            db.execute("UPDATE jobs SET status='interrupted', ended=?, result=? WHERE status='running'", (self.now(), json.dumps('Container stopped during job. Re-run to resume downloaded documents.')))
            db.execute('CREATE TABLE IF NOT EXISTS schedule (key TEXT PRIMARY KEY, value TEXT)')
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()
    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()
    def start(self, source, parameters):
        job_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)', (job_id,self.now(),None,'running',source,json.dumps(parameters),json.dumps({})))
        return job_id
    def progress(self, job_id, result):
        with self.connect() as db:
            db.execute('UPDATE jobs SET result=? WHERE id=?', (json.dumps(result),job_id))
    def finish(self, job_id, status, result):
        with self.connect() as db:
            db.execute('UPDATE jobs SET ended=?, status=?, result=? WHERE id=?', (self.now(),status,json.dumps(result),job_id))
    def history(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY started DESC LIMIT 50')]
    def get(self, key, fallback):
        with self.connect() as db:
            row = db.execute('SELECT value FROM schedule WHERE key=?', (key,)).fetchone()
        return row[0] if row else fallback
    def set(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO schedule VALUES (?,?)', (key,value))


