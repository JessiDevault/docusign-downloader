import csv
from contextlib import contextmanager
import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import UUID


ENVELOPE_STATUSES = ('completed',)


def selection_filters(statuses='completed', template_ids=''):
    statuses = tuple(dict.fromkeys(x.strip().lower() for x in statuses.split(',') if x.strip()))
    if not statuses or any(x not in ENVELOPE_STATUSES for x in statuses):
        raise ValueError('Only completed envelopes can be selected')
    templates = tuple(dict.fromkeys(str(UUID(x.strip())) for x in template_ids.split(',') if x.strip()))
    if len(templates) > 50:
        raise ValueError('Select at most 50 templates')
    return statuses, templates


class Settings:
    def __init__(self):
        self.config = Path(os.getenv('CONFIG_DIR', '/config'))
        self.data = Path(os.getenv('DATA_DIR', '/data'))
        self.downloads = Path(os.getenv('DOWNLOAD_DIR', '/downloads'))
        self.logs = Path(os.getenv('LOG_DIR', '/logs'))
        for folder in (self.config, self.data, self.downloads, self.logs):
            folder.mkdir(parents=True, exist_ok=True)
        self.auth_host = os.getenv('DOCUSIGN_AUTH_HOST', 'account-d.docusign.com')
        if self.auth_host not in ('account.docusign.com', 'account-d.docusign.com'):
            raise ValueError('DOCUSIGN_AUTH_HOST must be a DocuSign OAuth host')
        self.client_id = os.getenv('DOCUSIGN_CLIENT_ID', '')
        self.user_id = os.getenv('DOCUSIGN_USER_ID', '')
        self.account_id = os.getenv('DOCUSIGN_ACCOUNT_ID', '')
        self.key = self.config / 'private-key.pem'
        self.db = self.data / 'downloads.sqlite3'
        self.password = os.getenv('APP_PASSWORD', '')
        self.username = os.getenv('APP_USERNAME', 'admin')


def safe_name(value):
    value = re.sub(r'[^\w .-]', '_', value, flags=re.UNICODE).strip(' .')
    return (value or 'contract')[:90]


def select_documents(documents, pattern=''):
    candidates = [d for d in documents
                  if str(d.get('documentId', '')).isdigit()
                  and d.get('type', '').lower() == 'content'
                  and 'certificate of completion' not in d.get('name', '').lower()]
    if pattern:
        matcher = re.compile(pattern, re.IGNORECASE)
        return [d for d in candidates if matcher.search(d.get('name', ''))]
    return candidates if len(candidates) == 1 else []


def date_range(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError('Start date must be on or before end date')
    # UI dates are completion dates in UTC; the upper boundary is exclusive.
    return first.isoformat() + 'T00:00:00Z', (last + timedelta(days=1)).isoformat() + 'T00:00:00Z'


class Client:
    def __init__(self, settings):
        import requests
        self.s = settings
        self.session = requests.Session()
        self.token = ''
        self.expires = 0
        self.base = ''
        self.account = ''

    def authenticate(self):
        import jwt
        if not all((self.s.client_id, self.s.user_id, self.s.account_id)) or not self.s.key.is_file():
            raise RuntimeError('Set DocuSign client, user and account IDs and place private-key.pem in /config')
        now = int(time.time())
        assertion = jwt.encode({'iss': self.s.client_id, 'sub': self.s.user_id,
                                'aud': self.s.auth_host, 'iat': now, 'exp': now + 3600,
                                'scope': 'signature impersonation'},
                               self.s.key.read_text(), algorithm='RS256')
        response = self.session.post('https://' + self.s.auth_host + '/oauth/token',
                                     data={'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                                           'assertion': assertion}, timeout=(10, 60))
        if response.status_code != 200:
            try:
                code = response.json().get('error', 'authentication_failed')
            except ValueError:
                code = 'authentication_failed'
            raise RuntimeError('DocuSign OAuth: ' + str(code) + '. Check integration environment and JWT consent.')
        body = response.json()
        self.token = body['access_token']
        self.expires = time.time() + int(body['expires_in']) - 120
        response = self.session.get('https://' + self.s.auth_host + '/oauth/userinfo',
                                    headers={'Authorization': 'Bearer ' + self.token}, timeout=(10, 60))
        response.raise_for_status()
        account = next((a for a in response.json()['accounts']
                        if a['account_id'] == self.s.account_id), None)
        if not account:
            raise RuntimeError('Configured DocuSign account is not accessible to this user')
        uri = account['base_uri'].rstrip('/')
        parsed = urlparse(uri)
        if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.docusign.net'):
            raise RuntimeError('Unexpected DocuSign API base URI')
        self.account = account['account_id']
        self.base = uri + '/restapi/v2.1/accounts/' + quote(self.account, safe='')

    def get(self, path, params=None, stream=False):
        import requests
        for attempt in range(6):
            if time.time() >= self.expires:
                self.authenticate()
            try:
                response = self.session.get(self.base + path,
                                           headers={'Authorization': 'Bearer ' + self.token},
                                           params=params, stream=stream, timeout=(10, 120), allow_redirects=False)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 5:
                    raise RuntimeError('DocuSign connection failed after retries') from None
                time.sleep(min(2 ** attempt, 30))
                continue
            if response.status_code == 401:
                response.close()
                self.expires = 0
                continue
            if response.status_code == 429 or response.status_code >= 500:
                retry = response.headers.get('Retry-After', '')
                reset = response.headers.get('X-RateLimit-Reset', '')
                delay = float(retry) if retry.isdigit() else min(2 ** attempt, 30)
                if reset.isdigit():
                    delay = max(delay, int(reset) - time.time() + 1)
                response.close()
                if attempt == 5:
                    raise RuntimeError('DocuSign service or rate limit prevented this request; retry later')
                time.sleep(max(1, min(delay, 3600)))
                continue
            if response.status_code != 200:
                code = 'request_failed'
                try:
                    code = response.json().get('errorCode', code)
                except ValueError:
                    pass
                status = response.status_code
                response.close()
                raise RuntimeError(f'DocuSign HTTP {status}: {code}')
            return response
        raise RuntimeError('DocuSign authentication retry limit reached')

    def envelopes(self, start, end, statuses='completed', sender_user_id=''):
        selected_statuses, _ = selection_filters(statuses)
        sender_user_id = str(UUID(sender_user_id)) if sender_user_id else ''
        lower, upper = date_range(start, end)
        offset = 0
        seen = set()
        while True:
            with self.get('/envelopes', {'from_date': lower, 'to_date': upper,
                                        'status': ','.join(selected_statuses),
                                        'from_to_status': 'completed' if selected_statuses == ('completed',) else 'changed',
                                        'count': '100', 'start_position': str(offset),
                                        **({'user_filter': 'sender', 'user_id': sender_user_id} if sender_user_id else {})}) as response:
                page = response.json()
            envelopes = page.get('envelopes', [])
            if not envelopes:
                break
            for envelope in envelopes:
                eid = envelope['envelopeId']
                changed = envelope.get('completedDateTime', '') if selected_statuses == ('completed',) else envelope.get('statusChangedDateTime', '')
                if eid not in seen and envelope.get('status', '').lower() in selected_statuses and changed:
                    stamp = datetime.fromisoformat(changed.replace('Z', '+00:00'))
                    if date.fromisoformat(start) <= stamp.astimezone(timezone.utc).date() <= date.fromisoformat(end):
                        seen.add(eid)
                        yield envelope
            offset += len(envelopes)
            total = page.get('totalSetSize')
            if total is not None and offset >= int(total):
                break
            if not page.get('nextUri') and total is None:
                break

    def users(self):
        offset = 0
        users = {}
        while True:
            with self.get('/users', {'count': '100', 'start_position': str(offset)}) as response:
                page = response.json()
            batch = page.get('users', [])
            if not batch:
                break
            for user in batch:
                if user.get('userId'):
                    users[user['userId']] = {'id': user['userId'], 'name': user.get('userName', ''),
                                            'email': user.get('email', '')}
            offset += len(batch)
            total = page.get('totalSetSize')
            if (total is not None and offset >= int(total)) or (total is None and not page.get('nextUri')):
                break
            if offset >= 10000:
                raise RuntimeError('User directory exceeds the supported size')
        return sorted(users.values(), key=lambda u: (u['name'].casefold(), u['email'].casefold()))

    def envelope(self, eid):
        with self.get('/envelopes/' + quote(eid, safe='')) as response:
            return response.json()

    def templates(self, eid):
        with self.get('/envelopes/' + quote(eid, safe='') + '/templates') as response:
            return response.json().get('templates', [])

    def documents(self, eid):
        with self.get('/envelopes/' + quote(eid, safe='') + '/documents') as response:
            return response.json().get('envelopeDocuments', [])

    def download(self, eid, did, path):
        with self.get('/envelopes/' + quote(eid, safe='') + '/documents/' + quote(did, safe=''), stream=True) as response:
            with path.open('wb') as output:
                for chunk in response.iter_content(65536):
                    if chunk:
                        output.write(chunk)
                output.flush()
                os.fsync(output.fileno())


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(65536), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def valid_pdf(path):
    with path.open('rb') as source:
        header = source.read(5)
        source.seek(max(0, path.stat().st_size - 1024))
        tail = source.read()
    return header == b'%PDF-' and b'%%EOF' in tail


class Runner:
    def __init__(self, settings, client=None):
        self.s = settings
        self.client = client or Client(settings)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS downloads (envelope TEXT, document TEXT, filename TEXT, sha256 TEXT, PRIMARY KEY(envelope, document))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.s.db, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def run(self, start, end, pattern='', limit=1, download=False, report=lambda message: None,
            statuses='completed', template_ids='', sender_user_id=''):
        selected_statuses, selected_templates = selection_filters(statuses, template_ids)
        sender_user_id = str(UUID(sender_user_id)) if sender_user_id else ''
        date_range(start, end)
        if limit < 1 or limit > 100000:
            raise ValueError('Envelope limit must be between 1 and 100000')
        if len(pattern) > 200:
            raise ValueError('Document pattern is too long')
        re.compile(pattern)
        counts = {'envelopes': 0, 'selected': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0, 'ambiguous': 0,
                  'template_excluded': 0, 'sender_excluded': 0}
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        inventory_path = self.s.data / ('inventory-' + stamp + '.csv')
        with inventory_path.open('w', newline='', encoding='utf-8') as inventory, (self.s.logs / 'downloads.csv').open('a', newline='', encoding='utf-8') as log:
            rows = csv.writer(inventory)
            rows.writerow(['envelope_id', 'completed_utc', 'subject', 'document_id', 'document_name', 'selection',
                           'envelope_status', 'status_changed_utc', 'template_ids'])
            events = csv.writer(log)
            for envelope in self.client.envelopes(start, end, ','.join(selected_statuses), **({'sender_user_id': sender_user_id} if sender_user_id else {})):
                if counts['envelopes'] >= limit:
                    break
                counts['envelopes'] += 1
                eid = envelope['envelopeId']
                did = ''
                temporary = None
                try:
                    envelope_status = envelope.get('status', '').lower()
                    # Also enforce locally so a surprising API result cannot download a wrong status.
                    if envelope_status not in selected_statuses:
                        continue
                    if sender_user_id:
                        sender = envelope.get('sender') or self.client.envelope(eid).get('sender', {})
                        if sender.get('userId', '').lower() != sender_user_id:
                            counts['sender_excluded'] += 1
                            rows.writerow([eid, envelope.get('completedDateTime'), envelope.get('emailSubject'), '', '', 'SENDER_EXCLUDED', envelope_status, '', ''])
                            inventory.flush()
                            report(dict(counts))
                            continue
                    templates = self.client.templates(eid) if selected_templates else []
                    used_templates = {str(t.get('templateId', '')).lower() for t in templates}
                    metadata = [envelope_status, envelope.get('statusChangedDateTime', ''), ';'.join(sorted(used_templates))]
                    if selected_templates and not used_templates.intersection(selected_templates):
                        counts['template_excluded'] += 1
                        rows.writerow([eid, envelope.get('completedDateTime'), envelope.get('emailSubject'), '', '', 'TEMPLATE_EXCLUDED'] + metadata)
                        inventory.flush()
                        report(dict(counts))
                        continue
                    documents = self.client.documents(eid)
                    selected = select_documents(documents, pattern)
                    selected_ids = {d['documentId'] for d in selected}
                    for document in documents:
                        rows.writerow([eid, envelope.get('completedDateTime'), envelope.get('emailSubject'), document.get('documentId'), document.get('name'), 'SELECTED' if document.get('documentId') in selected_ids else 'EXCLUDED'] + metadata)
                    inventory.flush()
                    if not selected:
                        counts['ambiguous'] += 1
                        events.writerow([stamp, eid, '', 'NO_MATCH_OR_AMBIGUOUS', ''])
                    for document in selected:
                        did = str(document['documentId'])
                        counts['selected'] += 1
                        if not download:
                            continue
                        record_id = eid
                        name = safe_name(envelope.get('emailSubject', 'Contract')) + '--' + safe_name(document.get('name', 'Contract')) + '--' + safe_name(eid) + '--' + did + '.pdf'
                        target = self.s.downloads / name
                        with self.connect() as db:
                            previous = db.execute('SELECT filename, sha256 FROM downloads WHERE envelope=? AND document=?', (record_id, did)).fetchone()
                        if previous:
                            existing = self.s.downloads / previous[0]
                            if existing.is_file() and digest(existing) == previous[1] and valid_pdf(existing):
                                counts['skipped'] += 1
                                events.writerow([stamp, eid, did, 'SKIPPED', previous[0]])
                                continue
                        temporary = target.with_suffix('.pdf.part')
                        self.client.download(eid, did, temporary)
                        if not valid_pdf(temporary):
                            raise RuntimeError('Response is not a complete PDF')
                        checksum = digest(temporary)
                        temporary.replace(target)
                        with self.connect() as db:
                            db.execute('INSERT OR REPLACE INTO downloads VALUES (?,?,?,?)', (record_id, did, name, checksum))
                        counts['downloaded'] += 1
                        events.writerow([stamp, eid, did, 'SUCCESS', name])
                except Exception as error:
                    if temporary and temporary.exists():
                        temporary.unlink()
                    counts['failed'] += 1
                    # Never log credential values, raw HTTP responses, or JWT assertions.
                    detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
                    events.writerow([stamp, eid, did, 'FAILED', detail])
                log.flush()
                report(dict(counts))
        return {'counts': counts, 'inventory': inventory_path.name, 'mode': 'download' if download else 'preview'}


