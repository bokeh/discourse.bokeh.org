"""Finalize local URL rewriting, including old CDN/short-url aliases."""
from collections import Counter
import json
from pathlib import Path
import re
from urllib.parse import urljoin,urlparse
from bs4 import BeautifulSoup
from chronicon.storage.database import ArchiveDatabase
from media import ROOT,SITE,ORIGIN,rows,upload_id,uploads

db=ArchiveDatabase(ROOT/'archive.sqlite')
db.connection.execute('PRAGMA synchronous=OFF')
topic_paths={t.id:f'/t/{t.slug}/{t.id}' for t in db.get_all_topics()}
canonical_lookup={v:k for k,v in topic_paths.items()}
positions={}
for tid,base in topic_paths.items():
    for index,p in enumerate(db.get_topic_posts(tid)):
        page=index//50+1
        positions[(tid,p.post_number)]=base+('/' if page==1 else f'/page-{page}.html')+f'#post-{p.post_number}'
categories={c.id:c for c in db.get_all_categories()}
originals=json.loads((ROOT/'download-report.json').read_text())
by_id={r['id']:r for r in originals['files']}
extra=json.loads((ROOT/'additional-media-report.json').read_text())
by_url={r['url']:r for r in extra['files']}
unavailable=Counter();links_outside_scope=Counter();files_used=set();posts_written=0

def rewrite(url,media=False):
    if not url or url.startswith('#'):return url
    absolute=urljoin(ORIGIN,url)
    uid=upload_id(url)
    if uid in by_id:
        files_used.add(uid);return '/'+by_id[uid]['path']
    if absolute in by_url:return '/'+by_url[absolute]['path']
    parsed=urlparse(absolute)
    if parsed.scheme not in ('https','http','mailto'):return '#'
    if parsed.hostname=='discourse.bokeh.org':
        parts=parsed.path.strip('/').split('/')
        tid=None;post_number=None
        if len(parts)>=3 and '/'+ '/'.join(parts[:3]) in canonical_lookup:
            tid=canonical_lookup['/'+'/'.join(parts[:3])]
            if len(parts)>3 and parts[3].isdigit():post_number=int(parts[3])
        elif len(parts)>=2 and parts[0]=='t' and parts[1].isdigit():
            tid=int(parts[1])
            if len(parts)>2 and parts[2].isdigit():post_number=int(parts[2])
        elif len(parts)>=3 and parts[0]=='t' and parts[2].isdigit():
            tid=int(parts[2])
            if len(parts)>3 and parts[3].isdigit():post_number=int(parts[3])
        if tid is not None:
            if tid in topic_paths:
                fragment=re.match(r'post-(\d+)',parsed.fragment)
                number=post_number or (int(fragment[1]) if fragment else None)
                if number and (tid,number) in positions:return positions[(tid,number)]
                if number:return absolute  # Deleted/private post targets stay outside the archive.
                return topic_paths[tid]+'/'+('#'+parsed.fragment if parsed.fragment else '')
            links_outside_scope[tid]+=1
        match=re.match(r'/c/(?:[^/]+/)?(\d+)',parsed.path)
        if match and int(match[1]) in categories:
            c=categories[int(match[1])];return f'/c/{c.slug}/{c.id}/'
    if media:
        unavailable[absolute]+=1
        return None
    return absolute

for number,p in enumerate(rows,1):
    soup=BeautifulSoup(p['cooked'] or '','html.parser')
    for node in soup.find_all(['script','style','iframe','object','embed','form','input','button','link','base','svg','meta']):
        if node.name=='iframe' and node.get('src'):
            a=soup.new_tag('a',href=node['src']);a.string='Open external interactive example ↗';node.replace_with(a)
        else:node.decompose()
    for node in list(soup.find_all(True)):
        if node.parent is None:continue
        for attr in list(node.attrs):
            if attr.startswith('on') or attr in ('style','srcset','autoplay','srcdoc','data-download-href'):del node[attr]
        for attr in ('href','src','poster'):
            value=node.get(attr)
            if not isinstance(value,str):continue
            local=rewrite(value,media=attr in ('src','poster'))
            if local is None:
                if node.name=='img':
                    a=soup.new_tag('a',href=urljoin(ORIGIN,value));a['class']='missing-media';a.string='[External image unavailable in archive]';node.replace_with(a);break
                else:del node[attr]
            else:node[attr]=local
        if node.parent is None:continue
        if node.name=='img' and str(node.get('src','')).endswith('.download'):
            a=soup.new_tag('a',href=node['src']);a['download']='';a.string=node.get('alt') or 'Download original image attachment';node.replace_with(a)
        if node.name in ('video','audio'):node['controls']=''
    db.connection.execute('UPDATE posts SET cooked=? WHERE id=?',(str(soup),p['id']))
    posts_written+=1
    if number%2000==0:db.connection.commit();print(f'Normalized {number}/{len(rows)} posts',flush=True)
db.connection.commit()
report={'posts':posts_written,'uploaded_files_used_in_content':len(files_used),'unavailable_external_media':dict(unavailable),'out_of_scope_topic_links':dict(links_outside_scope),'public_uploaded_file_download_failures':originals['failures'],'additional_media_download_failures':extra['failures']}
(ROOT/'media-final-report.json').write_text(json.dumps(report,indent=2))
db.close()
print(f'Normalized {posts_written} posts. Unavailable embedded media URLs: {len(unavailable)}. Public upload failures: {len(originals["failures"])}.',flush=True)
