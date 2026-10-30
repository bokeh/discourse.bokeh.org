"""Render the imported public snapshot using the approved Chronicon theme."""
import html
import json
from pathlib import Path
import shutil
import time
from urllib.parse import urlparse
from chronicon.storage.database import ArchiveDatabase
from chronicon.exporters.html_static import HTMLStaticExporter

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'site'
db=ArchiveDatabase(ROOT/'archive.sqlite')
db.connection.execute('PRAGMA synchronous=OFF')
topics=db.get_all_topics()
topic_map={t.id:t for t in topics}
routes=json.loads((ROOT/'source/post-routes.json').read_text())
report=json.loads((ROOT/'download-report.json').read_text())
counts=json.loads((ROOT/'capture-counts.json').read_text())
assert len(routes)==sum(db.get_topic_posts_count(t.id) for t in topics)

class FullExporter(HTMLStaticExporter):
    def generate_search_index(self):
        # Pagefind indexes the full rendered content after generation.
        pass

exporter=FullExporter(db,SITE,template_dir=ROOT/'templates',include_users=False,search_backend='static',posts_per_page=50,pagination_enabled=True)
class NormalizedHTML:
    # normalize.py has already sanitized HTML and resolved all media/link paths.
    def rewrite_with_full_resolution_links(self,content,*args,**kwargs):return content
    def enhance_emoji_with_unicode(self,content):return content
    def enhance_all_image_alt_text(self,content):return content
exporter.html_processor=NormalizedHTML()
exporter.env.globals.update(archive_categories=sorted(db.get_all_categories(),key=lambda c:[5,13,9].index(c.id)),archive_db=db)
print('Rendering',len(topics),'topics with all replies',flush=True)
exporter.export()
for name in ('bokeh.css','bokeh.js'):
    folder='css' if name.endswith('.css') else 'js'
    (SITE/'assets'/folder).mkdir(parents=True,exist_ok=True)
    shutil.copy(ROOT/name,SITE/'assets'/folder/name)
shutil.copy(ROOT/'bokeh-logo.svg',SITE/'assets/bokeh-logo.svg')
(SITE/'.nojekyll').write_text('')
(SITE/'assets/js/search-init.js').write_text("new PagefindUI({element:'#search',showSubResults:true,showImages:false,pageSize:10});")

# Small redirect pages preserve historical post URLs without duplicating long topics.
def redirect(path,target):
    path.parent.mkdir(parents=True,exist_ok=True)
    escaped=html.escape(target,quote=True)
    path.write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex"><meta http-equiv="refresh" content="0;url={escaped}"><title>Bokeh Discourse archive</title></head><body><a href="{escaped}">Open archived discussion</a></body></html>')

post_positions={}
for t in topics:
    base=f'/t/{t.slug}/{t.id}'
    redirect(SITE/'t'/str(t.id)/'index.html',base+'/')
    for index,p in enumerate(db.get_topic_posts(t.id)):
        page_number=index//50+1
        target=base+('/' if page_number==1 else f'/page-{page_number}.html')+f'#post-{p.post_number}'
        redirect(SITE/base.lstrip('/')/str(p.post_number)/'index.html',target)
        redirect(SITE/'t'/str(t.id)/str(p.post_number)/'index.html',target)
        post_positions[p.id]=target
    redirect(SITE/'t'/f'{t.id}.html',base+'/')

# Original /uploads/short-url paths resolve without retaining the running forum.
alphabet='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
by_id={f['id']:f for f in report['files']}
upload_data={}
for line in (ROOT/'source/public-export.jsonl').open():
    r=json.loads(line)
    if r['kind']=='upload':upload_data[r['data']['id']]=r['data']
for uid,u in upload_data.items():
    if uid not in by_id or not u.get('sha1'):continue
    n=int(u['sha1'],16);base62=''
    while n:n,r=divmod(n,62);base62=alphabet[r]+base62
    ext=u.get('extension') or ''
    # Unknown-extension aliases are directories with a link to preserved bytes.
    redirect(SITE/'uploads/short-url'/f'{base62}.{ext}'/'index.html','/'+by_id[uid]['path'])

files=sorted(report['files'],key=lambda f:f['filename'].lower())
for page,start in enumerate(range(0,len(files),100),1):
    items=[]
    for f in files[start:start+100]:
        name=html.escape(f['filename'])
        path='/'+f['path']
        items.append(f'<li><a href="{path}" download="{html.escape(f["filename"],quote=True)}">{name}</a> <small>· {f["bytes"]:,} bytes</small></li>')
    total=(len(files)+99)//100
    paging='<nav class="paging">'+(f'<a href="{ "index.html" if page==2 else "page-"+str(page-1)+".html"}">← Previous</a>' if page>1 else '')+f'<span>Page {page} of {total}</span>'+(f'<a href="page-{page+1}.html">Next →</a>' if page<total else '')+'</nav>'
    template=exporter.env.from_string('{% extends "base.html" %}{% block content %}<h1>Preserved attachments and media</h1><p>Original uploaded files and author avatars, preserved locally. Files are downloads; archived HTML/JavaScript attachments are not executed.</p>'+paging+'<ul class="attachment-list">'+''.join(items)+'</ul>'+paging+'{% endblock %}')
    path=SITE/'attachments'/('index.html' if page==1 else f'page-{page}.html')
    path.parent.mkdir(exist_ok=True)
    path.write_text(template.render(depth=1))

table=''.join(f'<tr><td>{html.escape(name)}</td><td>{c["topics"]:,}</td><td>{c["posts"]:,}</td></tr>' for name,c in counts['categories'].items())
content=f'<h1>Archive capture report</h1><p>Public snapshot captured {html.escape(counts["captured_at"])}. The live forum has not been modified.</p><table class="topic-table"><thead><tr><th>Category</th><th>Topics</th><th>Public posts</th></tr></thead><tbody>{table}</tbody></table><p>{len(files):,} original uploaded files and avatar files preserved. {len(report["failures"])} file downloads failed.</p><p>Deleted, hidden, author-withdrawn, private, unlisted, and staff-only whisper content is excluded. External projects remain links rather than embedded applications.</p>'
extra=json.loads((ROOT/'additional-media-report.json').read_text())
content+=f'<p>{len(extra["files"]):,} additional publicly embedded media files were preserved. {len(extra["failures"])} historical media references are unavailable from their sources.</p><details><summary>Unavailable historical media</summary><ul>'
for failure in extra['failures']:
    content+='<li><a href="'+html.escape(failure['url'],quote=True)+'">'+html.escape(failure['url'])+'</a> — '+html.escape(failure['error'])+'</li>'
content+='</ul></details><p>Twenty-one upload files have historical database SHA-1 inconsistencies; the preserved bytes match the stored S3 object ETags, and SHA-256 hashes are retained in the local download report.</p>'
template=exporter.env.from_string('{% extends "base.html" %}{% block content %}'+content+'{% endblock %}')
(SITE/'archive-report.html').write_text(template.render(depth=0))
(ROOT/'source/post-targets.json').write_text(json.dumps(post_positions))
db.close()
print('Rendered topic pages, category/index pagination, URL aliases, attachment library and project footer.',flush=True)
