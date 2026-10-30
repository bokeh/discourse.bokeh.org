"""Package only the deployable static site, with a checksum manifest."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'site'
files=sorted(p for p in SITE.rglob('*') if p.is_file())
archive=ROOT/'bokeh-discourse-archive.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as out:
    for index,p in enumerate(files,1):
        out.write(p,p.relative_to(SITE))
        if index%20000==0:print(f'Packaged {index}/{len(files)} files',flush=True)
with zipfile.ZipFile(archive) as out:
    assert len(out.infolist())==len(files)
    assert out.testzip() is None
manifest={'site_files':len(files),'site_bytes':sum(p.stat().st_size for p in files),
          'zip_bytes':archive.stat().st_size,'zip_sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),
          'public_snapshot_sha256':hashlib.file_digest((ROOT/'source/public-export.jsonl').open('rb'),'sha256').hexdigest(),
          'chronicon_version':'1.0.1','pagefind_version':'1.5.2'}
(ROOT/'package-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2),flush=True)
