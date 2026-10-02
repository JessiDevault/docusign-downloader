import base64
import hmac
import html
import json
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from .jobs import Jobs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from .core import Runner, Settings


def main():
    settings = Settings()
    if len(settings.password) < 16:
        raise SystemExit('APP_PASSWORD must contain at least 16 characters')
    runner = Runner(settings)
    lock = threading.Lock()
    state = {'running': False, 'result': 'Ready. Preview one envelope before downloading.'}
    csrf = secrets.token_urlsafe(32)
    jobs = Jobs(settings.db)
    auto_enabled = os.getenv('AUTO_ENABLED', 'false').lower() == 'true'
    auto_interval = max(300, int(os.getenv('AUTO_INTERVAL_SECONDS', '86400')))
    auto_start = os.getenv('AUTO_START_DATE', '')
    auto_pattern = os.getenv('DOCUMENT_NAME_PATTERN', '')
    if auto_enabled:
        from .core import date_range
        date_range(auto_start, datetime.now(timezone.utc).date().isoformat())
        re.compile(auto_pattern)

    def launch(start, end, pattern, limit, download, source):
        with lock:
            if state['running']:
                return False
            state.update(running=True, result='Starting')
        try:
            job_id = jobs.start(source, dict(start=start, end=end, pattern=pattern, limit=limit, download=download))
        except Exception:
            with lock:
                state['running'] = False
            raise
        def work():
            def progress(counts):
                jobs.progress(job_id, counts)
                with lock:
                    state['result'] = counts
            status = 'failed'
            try:
                result = runner.run(start, end, pattern, limit, download, progress)
                counts = result['counts']
                status = 'completed' if counts['failed'] == 0 and counts['ambiguous'] == 0 else 'needs_attention'
                # Retain a one-day overlap, and never advance past an incomplete batch.
                if source == 'automatic' and status == 'completed' and counts['envelopes'] < limit:
                    jobs.set('next_start', max(auto_start, (date.fromisoformat(end) - timedelta(days=1)).isoformat()))
            except Exception as error:
                result = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            finally:
                try:
                    jobs.finish(job_id, status, result)
                finally:
                    with lock:
                        state.update(running=False, result=result)
        threading.Thread(target=work, daemon=True).start()
        return True

    def scheduler():
        while True:
            next_due = float(jobs.get('next_due', '0'))
            if time.time() >= next_due:
                start = jobs.get('next_start', auto_start)
                if launch(start, datetime.now(timezone.utc).date().isoformat(), auto_pattern, 100000, True, 'automatic'):
                    jobs.set('next_due', str(time.time() + auto_interval))
            time.sleep(10)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, status, body, content_type='text/html; charset=utf-8'):
            payload = body.encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def authenticated(self):
            expected = 'Basic ' + base64.b64encode((settings.username + ':' + settings.password).encode()).decode()
            if hmac.compare_digest(self.headers.get('Authorization', ''), expected):
                return True
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="DocuSign downloader"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return False

        def do_GET(self):
            if self.path == '/health':
                self.send(200, 'ok', 'text/plain')
                return
            if not self.authenticated():
                return
            if self.path != '/':
                self.send(404, 'Not found')
                return
            with lock:
                status = html.escape(json.dumps(state, indent=2))
            rows = []
            for job in jobs.history():
                parameters = json.loads(job['parameters'])
                result = json.loads(job['result'])
                counts = result.get('counts', result) if isinstance(result, dict) else result
                if isinstance(counts, dict):
                    summary = ', '.join(f'{name}: {number}' for name, number in counts.items())
                else:
                    summary = str(counts)
                cells = [job['started'], job['status'], job['source'],
                         parameters.get('start', '') + ' to ' + parameters.get('end', ''),
                         'Download' if parameters.get('download') else 'Preview', summary]
                rows.append('<tr>' + ''.join('<td>' + html.escape(str(cell)) + '</td>' for cell in cells) + '</tr>')
            history = '<table><thead><tr><th>Started (UTC)</th><th>Status</th><th>Trigger</th><th>Date range</th><th>Mode</th><th>Results</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
            schedule_status = 'Enabled' if auto_enabled else 'Disabled'
            self.send(200, '''<!doctype html><html><meta charset="utf-8"><title>DocuSign downloader</title>
<style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:20px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #ddd;vertical-align:top}label{display:block;margin:16px 0}input{padding:8px}button{padding:12px}pre{white-space:pre-wrap;background:#eee;padding:20px}</style>
<h1>DocuSign contract downloader</h1><p>Start with Preview and an envelope limit of 1. Dates use completion dates in UTC. Certificates are excluded. Without a name filter, only single-document envelopes are selected.</p>
<form method="post" action="/run"><input type="hidden" name="csrf" value="''' + csrf + '''">
<label>First completion date <input required type="date" name="start"></label>
<label>Last completion date <input required type="date" name="end"></label>
<label>Envelope limit <input required type="number" name="limit" min="1" max="100000" value="1"></label>
<label>Contract filename filter (optional regular expression) <input name="pattern" maxlength="200" placeholder="Sales Contract"></label>
<label><input required type="radio" name="mode" value="preview" checked> Preview selection</label>
<label><input type="radio" name="mode" value="download"> Download selected contracts</label>
<label><input type="checkbox" name="confirm" value="yes"> I checked the preview inventory and approve downloading this selection.</label>
<button>Start</button></form><h2>Status</h2><p>Refresh this page to update progress. Inventory CSV files are saved in the host data folder.</p><pre>''' + status + '</pre><h2>Automatic schedule: ' + schedule_status + '</h2><h2>Recent jobs</h2>' + history + '</html>')

        def do_POST(self):
            if not self.authenticated():
                return
            if self.path != '/run':
                self.send(404, 'Not found')
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    raise ValueError('Invalid form size')
                fields = parse_qs(self.rfile.read(size).decode(), keep_blank_values=True)
                def value(name):
                    return fields.get(name, [''])[0]
                if not hmac.compare_digest(value('csrf'), csrf):
                    self.send(403, 'Refresh the page and try again')
                    return
                from .core import date_range
                start, end, pattern = value('start'), value('end'), value('pattern')
                limit = int(value('limit'))
                date_range(start, end)
                if not 1 <= limit <= 100000 or len(pattern) > 200:
                    raise ValueError('Invalid limit or filter length')
                re.compile(pattern)
                if value('mode') not in ('preview', 'download'):
                    raise ValueError('Invalid mode')
                download = value('mode') == 'download'
                if download and value('confirm') != 'yes':
                    raise ValueError('Check the download confirmation after reviewing the preview')
            except (ValueError, UnicodeError, re.error) as error:
                self.send(400, html.escape(str(error)))
                return
            if not launch(start, end, pattern, limit, download, 'manual'):
                self.send(409, 'A job is already running')
                return
            self.send_response(303)
            self.send_header('Location', '/')
            self.send_header('Content-Length', '0')
            self.end_headers()

    if auto_enabled:
        threading.Thread(target=scheduler, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8080'))), Handler).serve_forever()


if __name__ == '__main__':
    main()




