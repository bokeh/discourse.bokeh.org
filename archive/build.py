"""Full public-category archive from a read-only snapshot, rendered with Chronicon."""
from __future__ import annotations
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
from chronicon.storage.database import ArchiveDatabase
from chronicon.models.category import Category
from chronicon.models.topic import Topic
from chronicon.models.post import Post
from chronicon.models.user import User
from chronicon.exporters.html_static import HTMLStaticExporter

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'site'
SITE.mkdir(exist_ok=True)
ORIGIN='https://discourse.bokeh.org'
CDN='https://discourse-uploads.bokeh.org'
ALLOWED={5,9,13}

def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))

def log(message):
    print(time.strftime('%H:%M:%S'),message,flush=True)

rows=defaultdict(list)
for line in (ROOT/'source/public-export.jsonl').open():
    r=json.loads(line);rows[r['kind']].append(r['data'])
assert {c['id'] for c in rows['category']}==ALLOWED
topics={t['id']:t for t in rows['topic']}
assert all(t['category_id'] in ALLOWED for t in topics.values())
posts=rows['post']
counts=Counter(p['topic_id'] for p in posts)
assert all(counts[t['id']]==t['posts_count'] for t in topics.values())
assert len({p['id'] for p in posts})==len(posts)
uploads={u['id']:u for u in rows['upload']}
checksum_metadata={r['id']:r for r in map(json.loads,(ROOT/'source/checksum-metadata.jsonl').read_text().splitlines())} if (ROOT/'source/checksum-metadata.jsonl').exists() else {}
paths={tid:f'/t/{t["slug"]}/{tid}' for tid,t in topics.items()}
log(f'Snapshot: {len(topics)} topics, {len(posts)} public posts, {len(uploads)} public upload files')
save(ROOT/'capture-counts.json',{'captured_at':rows['capture'][0]['captured_at'],'categories':{c['name']:{'topics':sum(t['category_id']==c['id'] for t in topics.values()),'posts':sum(counts[t['id']] for t in topics.values() if t['category_id']==c['id'])} for c in rows['category']}})

def file_path(u):
    extension=(u.get('extension') or 'bin').lower()
    if extension not in {'png','jpg','jpeg','gif','webp','avif','tiff','bmp','mp4','webm','mov','mp3','wav','ogg','pdf','zip','gz','tar','rar','7z','csv','txt','log','json','ipynb','py','xlsx','xls','h5','hdf','pkl','pickle','patch','conf','service'}:
        extension='download'
    return SITE/'assets/uploads'/f'{u["id"]}-{u.get("sha1") or "file"}.{extension}'

def fetch_upload(u):
    target=file_path(u);target.parent.mkdir(parents=True,exist_ok=True)
    url=CDN+urlparse(u['url']).path
    for attempt in range(3):
        try:
            if not target.exists():
                request=Request(url,headers={'User-Agent':'Bokeh-public-static-archive/1.0'})
                with urlopen(request,timeout=25) as response:
                    content=response.read()
                assert not u['filesize'] or len(content)==u['filesize'], 'size mismatch'
                if u.get('sha1') and u['id'] not in checksum_metadata:
                    assert hashlib.sha1(content).hexdigest()==u['sha1'], 'SHA-1 mismatch'
                temporary=target.with_suffix(target.suffix+'.part')
                temporary.write_bytes(content);temporary.replace(target)
            content=target.read_bytes()
            assert not u['filesize'] or len(content)==u['filesize']
            sha1=hashlib.sha1(content).hexdigest()
            if u.get('sha1') and u['id'] not in checksum_metadata: assert sha1==u['sha1']
            if u['id'] in checksum_metadata:
                assert hashlib.md5(content).hexdigest()==str(checksum_metadata[u['id']]['etag']).strip('"'),'stored object ETag mismatch'
            return {'id':u['id'],'url':url,'path':str(target.relative_to(SITE)),'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'filename':u['original_filename'],'actual_sha1':sha1,'database_sha1':u.get('sha1'),'md5':hashlib.md5(content).hexdigest(),'database_etag':checksum_metadata.get(u['id'],{}).get('etag'),'checksum_exception':sha1!=u.get('sha1')}
        except Exception as error:
            if attempt==2:return {'id':u['id'],'url':url,'error':str(error)}
            time.sleep(attempt+1)

downloaded={};failures=[]
with ThreadPoolExecutor(max_workers=6) as pool:
    pending={pool.submit(fetch_upload,u):u['id'] for u in uploads.values()}
    for number, future in enumerate(as_completed(pending),1):
        result=future.result()
        if 'error' in result:failures.append(result)
        else:downloaded[result['id']]=result
        if number%100==0 or number==len(pending):
            log(f'Files: {number}/{len(pending)} checked, {len(failures)} failures')
            save(ROOT/'download-report.json',{'completed':number,'total':len(pending),'files':list(downloaded.values()),'failures':failures})

url_map={};short_map={};extra_media={};unresolved=Counter();attachment_ids=set()
alphabet='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
for uid,u in uploads.items():
    if uid not in downloaded:continue
    local='/'+downloaded[uid]['path']
    url_map[urlparse(u['url']).path]=local
    if u.get('sha1'):
        n=int(u['sha1'],16);s=''
        while n:n,r=divmod(n,62);s=alphabet[r]+s
        short_map[s]=local
for opt in rows['optimized']:
    if opt['upload_id'] in downloaded:url_map[urlparse(opt['url']).path]='/'+downloaded[opt['upload_id']]['path']

def local_url(value, media=False):
    if not value:return value
    if value.startswith('#'):return value
    absolute=urljoin(ORIGIN,value)
    parsed=urlparse(absolute)
    if parsed.scheme not in {'http','https','mailto'}:return '#'
    hostname=parsed.hostname or ''
    forum_host=hostname in {'discourse.bokeh.org','discourse-uploads.bokeh.org','bokeh-discourse-uploads.s3.dualstack.us-east-1.amazonaws.com','bokeh-discourse-uploads.s3.amazonaws.com'}
    if forum_host:
        path=unquote(parsed.path)
        target=url_map.get(path)
        short=re.search(r'/uploads/short-url/([0-9a-zA-Z]+)',path)
        if not target and short:target=short_map.get(short[1])
        if target:return target + ('#'+parsed.fragment if parsed.fragment else '')
        topic=re.match(r'/t/(?:[^/]+/)?(\d+)(?:/(\d+))?(?:\.json)?/?$',path)
        if topic and int(topic[1]) in paths:
            return paths[int(topic[1])]+'/'+((topic[2]+'/') if topic[2] else '')+('#'+parsed.fragment if parsed.fragment else '')
        category=re.match(r'/c/(?:[^/]+/)?(\d+)',path)
        if category and int(category[1]) in ALLOWED:
            c=next(c for c in rows['category'] if c['id']==int(category[1]))
            return f'/c/{c["slug"]}/{c["id"]}/'
        if media and ('/images/emoji/' in path or '/letter_avatar_proxy/' in path):
            extra_media[absolute]=None
            return absolute
        if '/original/' in path or '/optimized/' in path or '/uploads/' in path:
            unresolved[absolute]+=1
    elif media:
        extra_media[absolute]=None
    return absolute

def clean_cooked(cooked):
    soup=BeautifulSoup(cooked or '','html.parser')
    for node in soup.find_all(['script','style','iframe','object','embed','form','input','button','link','base']):
        if node.name=='iframe' and node.get('src'):
            a=soup.new_tag('a',href=node['src']);a.string='Open external interactive example ↗';node.replace_with(a)
        else:node.decompose()
    for node in soup.find_all(True):
        for attr in list(node.attrs):
            if attr.startswith('on') or attr in ('style','srcset','autoplay','srcdoc'):del node[attr]
        for attr in ('href','src','poster'):
            if isinstance(node.get(attr),str):node[attr]=local_url(node[attr],media=attr in ('src','poster'))
        if node.name=='video' or node.name=='audio':node['controls']=''
    return str(soup)

dbpath=ROOT/'archive.sqlite'
if dbpath.exists():dbpath.unlink()
db=ArchiveDatabase(dbpath)
db.connection.execute('PRAGMA synchronous=OFF')
for category in rows['category']:
    category['topic_count']=sum(t['category_id']==category['id'] for t in topics.values())
    db.insert_category(Category.from_dict(category))
db.update_site_metadata(ORIGIN,site_title='Bokeh Discourse',site_description='Public forum archive — local review')
db.set_category_filter(ORIGIN,sorted(ALLOWED))
for t in topics.values():
    if t.get('user_id') is not None and t['user_id']<=0:t['user_id']=None
    db.insert_topic(Topic.from_dict(t))
user_data={};post_routes={};plain_text={}
for number,p in enumerate(posts,1):
    if p['username']=='deleted-user' and p['user_id']>0:p['username']=f'deleted-user-{p["user_id"]}'
    p['cooked']=clean_cooked(p['cooked'])
    plain_text[p['id']]=BeautifulSoup(p['cooked'],'html.parser').get_text(' ',strip=True)
    db.insert_post(Post.from_dict(p))
    user_data[p['user_id']]=p
    post_routes[p['id']]=(p['topic_id'],p['post_number'])
    if number%2000==0:log(f'Imported {number}/{len(posts)} posts')
for uid,p in user_data.items():
    avatar=downloaded.get(p.get('avatar_upload_id'))
    if avatar:
        avatar_path=SITE/avatar['path']
    else:
        avatar_path=SITE/'assets/avatars'/f'{uid}.svg';avatar_path.parent.mkdir(parents=True,exist_ok=True)
        avatar_path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><rect width="48" height="48" fill="#'+hashlib.md5(p['username'].encode()).hexdigest()[:6]+'"/><text x="24" y="33" text-anchor="middle" font-family="Arial" font-size="28" fill="white">'+html.escape(p['username'][0].upper())+'</text></svg>')
    db.insert_user(User(id=uid,username=p['username'],name=p.get('name'),avatar_template='',trust_level=0,created_at=None,local_avatar_path=str(avatar_path)))

# Keep all HTML asset paths root-relative. No second live-site dependency is introduced.
log(f'Found {len(extra_media)} additional media URLs and {len(unresolved)} unresolved uploaded-file URLs')
save(ROOT/'media-to-review.json',{'additional_media':list(extra_media),'unresolved_upload_urls':dict(unresolved)})
save(ROOT/'source/post-routes.json',{str(k):v for k,v in post_routes.items()})
save(ROOT/'source/plain-text.json',plain_text)
db.close()
log('Public database import complete; ready to render')
