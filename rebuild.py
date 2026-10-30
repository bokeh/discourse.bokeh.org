"""Rebuild the frozen public archive using only GitHub-hosted capture inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / 'archive'
CACHE = ROOT / '.cache'
REPOSITORY = 'bokeh/discourse.bokeh.org'

def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def asset(manifest, filename):
    CACHE.mkdir(exist_ok=True)
    target = CACHE / filename
    if not target.exists():
        url = f'https://github.com/{REPOSITORY}/releases/download/{quote(manifest["tag"])}/{quote(filename)}'
        print('Downloading', filename, flush=True)
        temporary = target.with_suffix('.part')
        with urlopen(Request(url, headers={'User-Agent': 'Bokeh-archive-rebuild/1.0'}), timeout=120) as source:
            with temporary.open('wb') as output:
                while block := source.read(1024 * 1024): output.write(block)
        temporary.replace(target)
    assert sha256(target) == manifest['sha256'], f'Checksum mismatch: {filename}'
    return target

def extract(path, destination, assets_only=False):
    with zipfile.ZipFile(path) as bundle:
        assert bundle.testzip() is None, f'Corrupt bundle: {path.name}'
        for record in bundle.infolist():
            member = Path(record.filename)
            assert not member.is_absolute() and '..' not in member.parts
            if not assets_only or record.filename.startswith('assets/'):
                bundle.extract(record, destination)

def stage(name):
    # The capture stages must never fall back to the live forum or its media hosts.
    runner = """import runpy, sys, urllib.request, socket
def offline(*args, **kwargs):
    raise RuntimeError('Network access is disabled during frozen-snapshot rebuilding')
urllib.request.urlopen = offline
socket.create_connection = offline
socket.socket.connect = offline
sys.path.insert(0, sys.argv[1])
runpy.run_path(sys.argv[2], run_name='__main__')
"""
    print('Running', name, flush=True)
    subprocess.run([sys.executable, '-c', runner, str(ARCHIVE), str(ARCHIVE / name)], cwd=ROOT, check=True)

def main():
    source = json.loads((ROOT / 'source-snapshot.json').read_text())
    rendered = json.loads((ROOT / 'snapshot.json').read_text())
    extract(asset(source, source['asset']), ARCHIVE)
    assert sha256(ARCHIVE / 'source/public-export.jsonl') == source['public_export_sha256']
    # Only preserved assets are seeded from the old rendered ZIP. HTML, database,
    # URL aliases, category pages, and search are regenerated from the public JSON.
    extract(asset(rendered, 'bokeh-discourse-archive.zip'), ARCHIVE / 'site', assets_only=True)
    for name in ['build.py', 'normalize.py', 'render.py', 'finalize.py']: stage(name)
    uploads = json.loads((ARCHIVE / 'download-report.json').read_text())
    assert not uploads['failures'] and len(uploads['files']) == source['uploads']
    subprocess.run(['npx', '--yes', 'pagefind@1.5.2', '--site', str(ARCHIVE / 'site'),
                    '--glob', 't/*/*/*.html'], cwd=ROOT, check=True)
    stage('validate.py')
    validation = json.loads((ARCHIVE / 'validation.json').read_text())
    assert validation['rendered_posts'] == source['posts']
    assert validation['additional_media_files'] == source['additional_media']
    stage('package.py')
    print('Rebuilt archive:', ARCHIVE / 'bokeh-discourse-archive.zip', flush=True)

if __name__ == '__main__': main()
