"""Disposable local backend for real API QA, with no inherited credentials.

Requires QA Mongo on 127.0.0.1:27028 and Redis on 127.0.0.1:6379.
Uses only the vandalizer_ra8_20261001 database and /private/tmp storage.
SMTP is captured locally; outbound socket connections are limited to QA ports.
"""
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import socketserver
import sys
import threading
import uuid

repo = Path(__file__).resolve().parents[3]
run = Path('/private/tmp/vandalizer-ra8-backend')
run.mkdir(mode=0o700, parents=True, exist_ok=True)
(run / 'mail').mkdir(exist_ok=True)
os.chdir(run)
sys.path.insert(0, str(repo / 'backend'))
os.environ.clear()
os.environ.update({
    'PATH': '/usr/local/bin:/usr/bin:/bin',
    'MONGO_HOST': 'mongodb://127.0.0.1:27028/', 'MONGO_DB': 'vandalizer_ra8_20261001',
    'REDIS_HOST': '127.0.0.1', 'FRONTEND_URL': 'http://127.0.0.1:5181',
    'UPLOAD_DIR': str(run / 'uploads'), 'CHROMADB_PERSIST_DIR': str(run / 'chroma'),
    'DISABLE_UPDATE_CHECK': 'true', 'PROMOTIONAL_EMAILS_ENABLED': 'false',
    'TELEMETRY_ENABLED': 'false', 'ENABLE_TRIAL_SYSTEM': 'false',
    'SMTP_HOST': '127.0.0.1', 'SMTP_PORT': '8025', 'SMTP_START_TLS': 'false',
    'SMTP_FROM_EMAIL': 'qa@example.test', 'ENVIRONMENT': 'development', 'COOKIE_SECURE': 'false',
    'LOG_FORMAT': 'text',
})
runtime_file = run / 'runtime.json'
if runtime_file.exists():
    runtime = json.loads(runtime_file.read_text())
else:
    runtime = {'password': secrets.token_urlsafe(20), 'jwt_secret': secrets.token_urlsafe(48)}
    runtime_file.write_text(json.dumps(runtime))
    runtime_file.chmod(0o600)
os.environ['JWT_SECRET_KEY'] = runtime['jwt_secret']

original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
def permitted(address):
    if not isinstance(address, tuple) or address[0] not in ('127.0.0.1', 'localhost', '::1') or address[1] not in (27028, 6379, 8025):
        raise OSError('Isolated QA blocks connections outside its local database/cache/mail ports')
def connect(sock, address):
    permitted(address)
    return original_connect(sock, address)
def connect_ex(sock, address):
    permitted(address)
    return original_connect_ex(sock, address)
socket.socket.connect = connect
socket.socket.connect_ex = connect_ex

class MailSink(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'220 localhost isolated QA SMTP\r\n')
        while line := self.rfile.readline():
            command = line.decode(errors='replace').strip().upper()
            if command.startswith(('EHLO', 'HELO')):
                self.wfile.write(b'250-localhost\r\n250 SIZE 10485760\r\n')
            elif command == 'DATA':
                self.wfile.write(b'354 End with a single dot\r\n')
                body = bytearray()
                while (line := self.rfile.readline()) and line != b'.\r\n':
                    body.extend(line[1:] if line.startswith(b'..') else line)
                path = run / 'mail' / f'{uuid.uuid4()}.eml'
                path.write_bytes(body)
                path.chmod(0o600)
                self.wfile.write(b'250 Captured locally\r\n')
            elif command == 'QUIT':
                self.wfile.write(b'221 Bye\r\n')
                break
            else:
                self.wfile.write(b'250 OK\r\n')

class MailServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

async def seed():
    from app.config import Settings
    from app.database import init_db, get_client
    from app.models.user import User
    from app.models.system_config import SystemConfig
    from app.utils.security import hash_password
    await init_db(Settings())
    await SystemConfig.get_config()
    for role in ['owner', 'member', 'viewer', 'outsider', 'admin']:
        identity = f'ra8-{role}@example.test'
        if not await User.find_one(User.user_id == identity):
            await User(user_id=identity, email=identity, name=f'QA {role.title()}', password_hash=hash_password(runtime['password']), email_verified=True, is_admin=role == 'admin', is_staff=role == 'admin', is_examiner=role == 'admin').insert()
    get_client().close()

if __name__ == '__main__':
    asyncio.run(seed())
    smtp = MailServer(('127.0.0.1', 8025), MailSink)
    threading.Thread(target=smtp.serve_forever, daemon=True).start()
    import uvicorn
    try:
        uvicorn.run('app.main:app', host='127.0.0.1', port=8001, access_log=False)
    finally:
        smtp.shutdown()
        smtp.server_close()
