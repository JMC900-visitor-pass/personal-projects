"""Local-only HTTP server for the skirmish creator."""
import json
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .generator import generate_brief, parse_brief
from .library import Library
from .llm import models
from .skirmish import ROOT

MAX_JOBS = 10


class Job:
    """One generation run; keeps every event so a late viewer can replay it."""

    def __init__(self):
        self.id = secrets.token_urlsafe(16)
        self.events = []
        self.done = False
        self.changed = threading.Condition()

    def push(self, event):
        with self.changed:
            self.events.append(event)
            self.changed.notify_all()

    def finish(self, event):
        with self.changed:
            self.events.append(event)
            self.done = True
            self.changed.notify_all()


ASSETS = {'/': ('skirmish.html', 'text/html'), '/skirmish.js': ('skirmish.js', 'text/javascript'),
          '/skirmish.css': ('skirmish.css', 'text/css')}


def serve(library=None, port=8765):
    library = library or Library()
    token = secrets.token_urlsafe(32)
    generation_lock = threading.Lock()
    jobs = {}

    def run(job, brief):
        try:
            packet = generate_brief(brief, progress=job.push)
            job.push({'type': 'step', 'id': 'save', 'status': 'running', 'detail': ''})
            packet = library.save(packet)
            job.push({'type': 'step', 'id': 'save', 'status': 'done', 'detail': packet['saved_id']})
            job.finish({'type': 'complete', 'saved_id': packet['saved_id'], 'name': packet['scenario']['name']})
        except ValueError as exc:
            job.finish({'type': 'error', 'message': str(exc)})
        except Exception:
            traceback.print_exc()
            job.finish({'type': 'error', 'message': 'Unexpected server error; see terminal log'})
        finally:
            generation_lock.release()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def respond(self, status, body, content_type='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = (json.dumps(body) if content_type.startswith('application/json') else body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            self.wfile.write(body)

        def stream(self, job):
            """Server-Sent Events: replay the job so far, then follow it live."""
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            sent = 0
            try:
                while True:
                    with job.changed:
                        if sent >= len(job.events) and not job.done:
                            job.changed.wait(timeout=15)
                        batch, finished = job.events[sent:], job.done
                    sent += len(batch)
                    chunk = ''.join(f'data: {json.dumps(event)}\n\n' for event in batch) or ': waiting\n\n'
                    self.wfile.write(chunk.encode('utf-8'))
                    self.wfile.flush()
                    if finished and sent >= len(job.events):
                        return
            except (BrokenPipeError, ConnectionResetError):
                return

        def trusted_host(self):
            allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
            if self.headers.get('Host') not in allowed:
                self.respond(403, {'error': 'Local host only'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://{host}' for host in allowed}:
                self.respond(403, {'error': 'Cross-origin requests are not allowed'})
                return False
            return True

        def do_GET(self):
            if not self.trusted_host():
                return
            path = urlparse(self.path).path
            try:
                if path in ASSETS:
                    name, content_type = ASSETS[path]
                    self.respond(200, (ROOT / 'web' / name).read_bytes(), content_type + '; charset=utf-8')
                elif path == '/rules':
                    self.respond(200, (ROOT / 'docs' / 'CORE-RULES.md').read_text(encoding='utf-8'),
                                 'text/markdown; charset=utf-8')
                elif path == '/api/session':
                    self.respond(200, {'token': token})
                elif path == '/api/rules':
                    self.respond(200, {'markdown': (ROOT / 'docs' / 'CORE-RULES.md').read_text(encoding='utf-8')})
                elif path == '/api/skirmishes':
                    self.respond(200, library.list())
                elif path.startswith('/api/skirmishes/'):
                    self.respond(200, library.get(path.rsplit('/', 1)[1]))
                elif path.startswith('/api/jobs/') and path.endswith('/events'):
                    job = jobs.get(path.split('/')[3])
                    if job is None:
                        raise ValueError('Unknown generation job')
                    self.stream(job)
                elif path == '/api/models':
                    self.respond(200, models())
                else:
                    self.respond(404, {'error': 'Not found'})
            except ValueError as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                traceback.print_exc()
                self.respond(500, {'error': 'Unexpected server error; see terminal log'})

        def do_POST(self):
            if not self.trusted_host():
                return
            if not secrets.compare_digest(self.headers.get('X-Raid-Token', ''), token):
                self.respond(403, {'error': 'Reload the page to refresh the session token'})
                return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.respond(415, {'error': 'Use application/json'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Request must be 1–16384 bytes')
                data = json.loads(self.rfile.read(length))
                if urlparse(self.path).path != '/api/generate':
                    self.respond(404, {'error': 'Not found'})
                    return
                brief = parse_brief(data)
                if not generation_lock.acquire(blocking=False):
                    self.respond(409, {'error': 'A skirmish is already being generated. Wait for it to finish.'})
                    return
                job = Job()
                for old in list(jobs)[:-MAX_JOBS + 1]:
                    jobs.pop(old, None)
                jobs[job.id] = job
                threading.Thread(target=run, args=(job, brief), daemon=True).start()
                self.respond(202, {'job_id': job.id})
            except (ValueError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                traceback.print_exc()
                self.respond(500, {'error': 'Unexpected server error; see terminal log'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    print(f'Raidforge is ready: http://127.0.0.1:{port}', flush=True)
    print('Local only. Ctrl+C stops the server. Saved skirmishes: ' + str(library.folder), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()
