import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from downloader.core import Runner, Settings, Client, select_documents, date_range, selection_filters

PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'

class FakeClient:
    def __init__(self, broken=False):
        self.calls = 0
        self.broken = broken
    def envelopes(self, start, end, statuses='completed'):
        yield {'envelopeId': 'test-envelope', 'emailSubject': 'Building contract', 'status': 'completed', 'completedDateTime': '2026-01-01T12:00:00Z'}
    def templates(self, eid):
        return [{'templateId': '11111111-1111-1111-1111-111111111111', 'name': 'Contract'}]
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

    def test_template_match_and_exclusion(self):
        runner = Runner(self.settings, FakeClient())
        match = runner.run('2026-01-01', '2026-01-02', template_ids='11111111-1111-1111-1111-111111111111')
        self.assertEqual(match['counts']['selected'], 1)
        excluded = runner.run('2026-01-01', '2026-01-02', download=True, template_ids='22222222-2222-2222-2222-222222222222')
        self.assertEqual(excluded['counts']['template_excluded'], 1)
        self.assertEqual(excluded['counts']['downloaded'], 0)
        self.assertEqual(excluded['counts']['ambiguous'], 0)

    def test_only_completed_can_download(self):
        runner = Runner(self.settings, FakeClient())
        with self.assertRaises(ValueError):
            runner.run('2026-01-01', '2026-01-02', statuses='sent', download=True)
        for status in ('sent', '', 'signed'):
            with patch.object(runner.client, 'envelopes', return_value=iter([{'envelopeId': 'x', 'status': status}])):
                result = runner.run('2026-01-01', '2026-01-02', download=True)
                self.assertEqual(result['counts']['downloaded'], 0)

    def test_sender_and_template_must_both_match(self):
        client = FakeClient()
        sender = '33333333-3333-3333-3333-333333333333'
        envelope = {'envelopeId': 'x', 'status': 'completed', 'sender': {'userId': sender}}
        with patch.object(client, 'envelopes', return_value=iter([envelope])):
            result = Runner(self.settings, client).run('2026-01-01', '2026-01-02', sender_user_id=sender,
                template_ids='11111111-1111-1111-1111-111111111111')
            self.assertEqual(result['counts']['selected'], 1)
        with patch.object(client, 'envelopes', return_value=iter([envelope])):
            result = Runner(self.settings, client).run('2026-01-01', '2026-01-02', sender_user_id='44444444-4444-4444-4444-444444444444', download=True)
            self.assertEqual(result['counts']['sender_excluded'], 1)
            self.assertEqual(client.calls, 0)

    def test_invalid_filters(self):
        for statuses, templates in [('', ''), ('unknown', ''), ('completed', 'not-a-template-id')]:
            with self.assertRaises(ValueError):
                selection_filters(statuses, templates)
        self.assertEqual(selection_filters('Completed,completed')[0], ('completed',))

    def test_api_filters_pagination_and_date_boundaries(self):
        from unittest.mock import MagicMock
        client = Client.__new__(Client)
        first = MagicMock()
        first.__enter__.return_value.json.return_value = {'envelopes': [
            {'envelopeId':'a','status':'completed','completedDateTime':'2026-01-01T12:00:00Z'},
            {'envelopeId':'outside','status':'completed','completedDateTime':'2026-01-02T00:00:00Z'}], 'totalSetSize':'3'}
        second = MagicMock()
        second.__enter__.return_value.json.return_value = {'envelopes': [
            {'envelopeId':'b','status':'completed','completedDateTime':'2026-01-01T23:59:59Z'}], 'totalSetSize':'3'}
        with patch.object(client, 'get', side_effect=[first, second]) as get:
            result = list(client.envelopes('2026-01-01','2026-01-01',sender_user_id='33333333-3333-3333-3333-333333333333'))
        self.assertEqual([e['envelopeId'] for e in result], ['a','b'])
        self.assertEqual(get.call_args_list[0].args[1]['status'], 'completed')
        self.assertEqual(get.call_args_list[0].args[1]['from_to_status'], 'completed')
        self.assertEqual(get.call_args_list[0].args[1]['user_filter'], 'sender')
        self.assertEqual(get.call_args_list[0].args[1]['user_id'], '33333333-3333-3333-3333-333333333333')
        self.assertEqual(get.call_args_list[1].args[1]['start_position'], '2')

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

class DirectoryTests(unittest.TestCase):
    def test_duplicate_names_and_unselected_input(self):
        from downloader.users import UserDirectory
        from unittest.mock import MagicMock
        client = MagicMock()
        client.users.return_value = [{'id': 'a', 'name': 'Sam', 'email': 'sam@a.com'}, {'id': 'b', 'name': 'Sam', 'email': 'sam@b.com'}]
        directory = UserDirectory(lambda: client)
        users = directory.all()
        self.assertEqual(directory.resolve(users[1]['label']), 'b')
        self.assertEqual(directory.resolve(''), '')
        with self.assertRaises(ValueError):
            directory.resolve('Sam')
        client.users.assert_called_once()
        client.session.close.assert_called_once()

    def test_directory_failure_does_not_broaden_selection(self):
        from downloader.users import UserDirectory
        from unittest.mock import MagicMock
        client = MagicMock()
        client.users.side_effect = RuntimeError('DocuSign HTTP 403')
        with self.assertRaises(RuntimeError):
            UserDirectory(lambda: client).resolve('Sam')
        client.session.close.assert_called_once()

    def test_account_users_are_paginated(self):
        from unittest.mock import MagicMock
        client = Client.__new__(Client)
        responses = []
        for user_id in ('a', 'b'):
            response = MagicMock()
            response.__enter__.return_value.json.return_value = {'users': [{'userId': user_id, 'userName': 'Sam'}], 'totalSetSize': '2'}
            responses.append(response)
        with patch.object(client, 'get', side_effect=responses) as get:
            self.assertEqual([u['id'] for u in client.users()], ['a', 'b'])
            self.assertEqual(get.call_args_list[1].args[1]['start_position'], '1')
