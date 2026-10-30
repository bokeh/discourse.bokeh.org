"""Check every generated local link, post, and preserved-file checksum."""
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin,urlparse,unquote

ROOT=Path(__file__).resolve().parent;SITE=(ROOT/'site').resolve()
missing=Counter();remote_media=Counter();articles=Counter();page_ids={};fragment_checks=[]
class Audit(HTMLParser):
    def __init__(self,page):super().__init__();self.page=page;self.ids=set()
    def handle_starttag(self,tag,attributes):
        a=dict(attributes)
        if a.get('id'):self.ids.add(a['id'])
        if tag=='article' and a.get('class')=='post':articles[a.get('id')]+=1
        if tag in ('img','source','video','audio','script') and a.get('src','').startswith(('http:','https:','//')):remote_media[a['src']]+=1
        for key in ('href','src','poster'):
            value=a.get(key)
            if not value or value.startswith(('http:','https:','mailto:','data:')):continue
            parsed=urlparse(urljoin(self.page.as_uri(),value))
            path=Path(unquote(parsed.path)) if not value.startswith('/') else SITE/unquote(parsed.path).lstrip('/')
            if path.is_dir():path=path/'index.html'
            if not path.exists():missing[str(path)]+=1
            if parsed.fragment.startswith('post-') and path.suffix=='.html':fragment_checks.append((path,parsed.fragment))
html_pages=[p for p in SITE.rglob('*.html') if p.is_file()]
rendered_post_count=0
for index,page in enumerate(html_pages,1):
    content=page.read_text();audit=Audit(page);audit.feed(content);page_ids[page]=audit.ids
    rendered_post_count+=sum(s.startswith('post-') and s[5:].isdigit() for s in audit.ids)
    if index%20000==0:print(f'Checked {index}/{len(html_pages)} HTML pages',flush=True)
broken_fragments=[{'path':str(path.relative_to(SITE)),'fragment':fragment} for path,fragment in fragment_checks if path in page_ids and fragment not in page_ids[path]]
downloads=json.loads((ROOT/'download-report.json').read_text())
for record in downloads['files']:
    content=(SITE/record['path']).read_bytes()
    assert hashlib.sha256(content).hexdigest()==record['sha256']
    if record.get('checksum_exception'):assert record['md5']==str(record['database_etag']).strip('"')
extra=json.loads((ROOT/'additional-media-report.json').read_text())
for record in extra['files']:assert hashlib.sha256((SITE/record['path']).read_bytes()).hexdigest()==record['sha256']
counts=json.loads((ROOT/'capture-counts.json').read_text())
expected_posts=sum(c['posts'] for c in counts['categories'].values())
assert rendered_post_count==expected_posts,(rendered_post_count,expected_posts)
size=sum(p.stat().st_size for p in SITE.rglob('*') if p.is_file())
result={'html_pages':len(html_pages),'rendered_posts':rendered_post_count,'expected_posts':expected_posts,'original_files':len(downloads['files']),'additional_media_files':len(extra['files']),'unavailable_media_sources':len(extra['failures']),'site_bytes':size,'below_1GB':size<1_000_000_000,'missing_local_targets':dict(missing),'broken_post_fragments':broken_fragments,'remote_embedded_media':dict(remote_media),'checksum_verification':'all preserved original files and additional media SHA-256 verified; SHA-1 exceptions also match stored object ETags'}
(ROOT/'validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('missing_local_targets','broken_post_fragments','remote_embedded_media')},indent=2),flush=True)
print('Missing targets:',len(missing),'broken post anchors:',len(broken_fragments),'remote embedded media:',len(remote_media),flush=True)
assert not missing, 'See missing_local_targets in validation.json'
assert not broken_fragments, 'See broken_post_fragments in validation.json'
assert not remote_media, 'Unexpected live media dependencies'
