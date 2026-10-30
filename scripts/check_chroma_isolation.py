#!/usr/bin/env python3
"""Exercise the shipped Chroma boundary using disposable local Docker resources.

No app volumes, host ports, credentials, or deployed services are used. Docker
must already have the pinned Chroma image and nginx:alpine available locally.
The assertions validate compensating controls, not an upstream security patch.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def docker(*args: str) -> str:
    return subprocess.check_output(['docker', *args], text=True, cwd=ROOT).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pull', action='store_true', help='Pull the required test images first')
    args = parser.parse_args()
    # Some Compose versions require env_file paths to exist even with
    # --no-env-resolution. Render unchanged manifests beside an empty fixture;
    # never read, create, or replace the operator's real backend/.env.
    with TemporaryDirectory(prefix='vandalizer-chroma-config-') as directory:
        fixture = Path(directory)
        for name in ('compose.yaml', 'compose.prod.yaml'):
            shutil.copyfile(ROOT / name, fixture / name)
        (fixture / 'backend').mkdir()
        (fixture / 'backend' / '.env').touch()
        config = json.loads(subprocess.check_output(
            ['docker', 'compose', '-f', 'compose.yaml', '-f', 'compose.prod.yaml',
             'config', '--no-env-resolution', '--format', 'json'], cwd=fixture,
            env={**os.environ, 'VANDALIZER_VERSION': 'security-review'}, text=True))
    services = config['services']
    assert set(services['chromadb']['networks']) == {'chroma-private'}
    assert config['networks']['chroma-private']['internal'] is True
    assert not services['chromadb'].get('ports')
    assert 'chroma-private' not in services['frontend']['networks']
    assert all('chroma-private' in services[name]['networks'] for name in ('api', 'celery'))
    image = services['chromadb']['image']
    if args.pull:
        docker('pull', image)
        docker('pull', 'nginx:alpine')
    prefix = 'vandalizer-chroma-review-' + uuid4().hex[:10]
    private, public = prefix + '-private', prefix + '-public'
    server, peer = prefix + '-server', prefix + '-peer'
    created_networks: list[str] = []
    created_containers: list[str] = []
    try:
        docker('network', 'create', '--internal', private)
        created_networks.append(private)
        docker('network', 'create', public)
        created_networks.append(public)
        docker('run', '-d', '--pull=never', '--name', server, '--network', private,
               '--network-alias', 'chromadb', '-e', 'ANONYMIZED_TELEMETRY=FALSE',
               '-e', 'IS_PERSISTENT=FALSE', image)
        created_containers.append(server)
        docker('run', '-d', '--pull=never', '--name', peer, '--network', public, 'nginx:alpine')
        created_containers.append(peer)
        probe = '''import json, time, urllib.request, urllib.error
import chromadb
from chromadb.api.configuration import CollectionConfigurationInternal
from chromadb.server.fastapi.types import UpdateCollection
base = 'http://chromadb:8000/api/v2/tenants/default_tenant/databases/default_database'
for attempt in range(40):
    try:
        urllib.request.urlopen('http://chromadb:8000/api/v2/heartbeat', timeout=2).read()
        break
    except (OSError, urllib.error.URLError):
        if attempt == 39: raise
        time.sleep(1)
assert set(CollectionConfigurationInternal.definitions) == {'hnsw_configuration'}
assert 'new_configuration' not in UpdateCollection.model_fields
payload = {'_type': 'CollectionConfigurationInternal', 'embedding_function': {
    'type': 'known', 'name': 'sentence_transformer',
    'config': {'model_name': 'security-review-not-a-model', 'trust_remote_code': True}}}
try:
    CollectionConfigurationInternal.from_json(payload)
except ValueError as exc:
    assert 'Invalid parameter name: embedding_function' in str(exc)
else:
    raise AssertionError('Server accepted a remote embedding configuration')
def request(path, body, method):
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(base + path,
            None if body is None else json.dumps(body).encode(), {'Content-Type': 'application/json'}, method=method), timeout=5))
    except urllib.error.HTTPError as exc:
        raise AssertionError(method + ' ' + path + ': ' + exc.read().decode()) from exc
collection = request('/collections', {'name': 'security-review'}, 'POST')
# An unknown configuration field cannot reach a model loader in this version.
request('/collections/' + collection['id'], {'new_metadata': {'review': 'safe'},
    'new_configuration': payload}, 'PUT')
assert request('/collections/security-review', None, 'GET')['metadata'] == {'review': 'safe'}
print(json.dumps({'server_version': chromadb.__version__, 'backend_access': 'passed',
    'remote_embedding_configuration_rejected': True, 'update_configuration_field_absent': True}))
'''
        print(docker('run', '--rm', '--pull=never', '--network', private,
                     '--entrypoint', 'python', image, '-c', probe))
        server_ip = json.loads(docker('inspect', server))[0]['NetworkSettings']['Networks'][private]['IPAddress']
        peer_ip = json.loads(docker('inspect', peer))[0]['NetworkSettings']['Networks'][public]['IPAddress']
        denial = '''import socket
for host, port in TARGETS:
    try:
        with socket.create_connection((host, port), timeout=3): pass
    except OSError: continue
    raise AssertionError('Unexpected network access to ' + host)
print('network denial checks passed')
'''
        ingress = denial.replace('TARGETS', repr([('chromadb', 8000), (server_ip, 8000)]))
        # Prove the peer is listening before treating an egress refusal as isolation.
        ingress = 'import socket\nsocket.create_connection(' + repr((peer_ip, 80)) + ', timeout=3).close()\n' + ingress
        print(docker('run', '--rm', '--pull=never', '--network', public,
                     '--entrypoint', 'python', image, '-c', ingress))
        egress = denial.replace('TARGETS', repr([(peer_ip, 80)]))
        print(docker('exec', server, 'python', '-c', egress))
        print(json.dumps({'image': image, 'image_id': docker('image', 'inspect', image, '--format', '{{.Id}}'),
                          'frontend_to_chroma': 'denied', 'chroma_to_other_network': 'denied'}))
    finally:
        for name in reversed(created_containers):
            subprocess.run(['docker', 'rm', '-fv', name], check=True, stdout=subprocess.DEVNULL)
        for name in reversed(created_networks):
            subprocess.run(['docker', 'network', 'rm', name], check=True, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
