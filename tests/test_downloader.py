import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from downloader.core import Runner, Settings, select_documents, date_range

PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'

class FakeClient:
    def __init__(self, broken=False):
        self.calls = 0
        self.broken = broken
    def envelopes(self, start, end):
        yield {'envelopeId': 'test-envelope', 'emailSubject': 'Building contract', 'completedDateTime': '2026-01-01T12:00:00Z'}
    def documents(self, eid):
        return [{'documentId': '1', 'name': 'Contract.pdf', 'type': 'content'}, {'documentId': 'certificate', 'name': 'Certificate of Completion', 'type': 'summary'}]
    def download(self, eid, did, path):
        self.calls += 1
        path.write_bytes(b'<html>Error</html>' if self.broken else PDF)

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        env = {name: str(Path(self.temp.name) / folder) for name, folder in [('CONFIG_DIR','config'),('DATA_DIR','data'),('DOWNLOAD_DIR','downloads'),('LOG_DIR','logs')]}
        with patch.dict(os.environ, env):
            self.settings = Settings()
    def tearDown(self):
        self.temp.cleanup()
    def test_certificate_and_ambiguity(self):
        docs = FakeClient().documents('x')
        self.assertEqual([d['documentId'] for d in select_documents(docs)], ['1'])
        docs.append({'documentId':'2','name':'Terms.pdf','type':'content'})
        self.assertEqual(select_documents(docs), [])
        self.assertEqual([d['documentId'] for d in select_documents(docs, 'Contract')], ['1'])
    def test_preview_writes_inventory_without_download(self):
        client = FakeClient()
        result = Runner(self.settings, client).run('2026-01-01','2026-01-02')
        self.assertEqual(result['counts']['selected'], 1)
        self.assertEqual(client.calls, 0)
        self.assertTrue((self.settings.data/result['inventory']).exists())
    def test_resume_across_runner_recreation_and_corruption(self):
        client = FakeClient()
        self.assertEqual(Runner(self.settings, client).run('2026-01-01','2026-01-02',download=True)['counts']['downloaded'], 1)
        self.assertEqual(Runner(self.settings, client).run('2026-01-01','2026-01-02',download=True)['counts']['skipped'], 1)
        self.assertEqual(client.calls, 1)
        next(self.settings.downloads.glob('*.pdf')).write_bytes(b'corrupted')
        self.assertEqual(Runner(self.settings, client).run('2026-01-01','2026-01-02',download=True)['counts']['downloaded'], 1)
    def test_invalid_pdf_does_not_mark_success_and_retries(self):
        client = FakeClient(True)
        self.assertEqual(Runner(self.settings, client).run('2026-01-01','2026-01-02',download=True)['counts']['failed'], 1)
        self.assertEqual(list(self.settings.downloads.iterdir()), [])
        client.broken = False
        self.assertEqual(Runner(self.settings, client).run('2026-01-01','2026-01-02',download=True)['counts']['downloaded'], 1)
    def test_dates(self):
        self.assertEqual(date_range('2026-01-01','2026-01-01'), ('2026-01-01T00:00:00Z','2026-01-02T00:00:00Z'))
        with self.assertRaises(ValueError):
            date_range('2026-01-02','2026-01-01')

if __name__ == '__main__':
    unittest.main()

class JobHistoryTests(unittest.TestCase):
    def test_history_survives_recreation_and_marks_interrupted_jobs(self):
        from downloader.jobs import Jobs
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.sqlite'
            jobs = Jobs(path)
            finished = jobs.start('manual', {'download': False})
            jobs.finish(finished, 'completed', {'selected': 1})
            interrupted = jobs.start('automatic', {'download': True})
            jobs.set('next_start', '2026-01-01')
            recreated = Jobs(path)
            states = {row['id']: row['status'] for row in recreated.history()}
            self.assertEqual(states[finished], 'completed')
            self.assertEqual(states[interrupted], 'interrupted')
            self.assertEqual(recreated.get('next_start', ''), '2026-01-01')
