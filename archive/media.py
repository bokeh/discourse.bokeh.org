"""Capture publicly embedded media and normalize historical upload aliases."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import ipaddress
import json
import mimetypes
from pathlib import Path
import re
import socket
from urllib.parse import urljoin,urlparse,unquote
from urllib.request import Request,urlopen
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'site'
ORIGIN='https://discourse.bokeh.org'
rows=[];uploads={};optimized=[]
for line in (ROOT/'source/public-export.jsonl').open():
    r=json.loads(line)
    if r['kind']=='post':rows.append(r['data'])
    elif r['kind']=='upload':uploads[r['data']['id']]=r['data']
    elif r['kind']=='optimized':optimized.append(r['data'])
alphabet='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
sha_map={u['sha1']:u['id'] for u in uploads.values() if u.get('sha1')}
path_map={urlparse(u['url']).path:u['id'] for u in uploads.values()}
path_map.update({urlparse(o['url']).path:o['upload_id'] for o in optimized})
short_map={}
for sha,uid in sha_map.items():
    n=int(sha,16);s=''
    while n:n,r=divmod(n,62);s=alphabet[r]+s
    short_map[s]=uid

def upload_id(url):
    if urlparse(url).scheme=='upload':return short_map.get(urlparse(url).netloc.split('.')[0])
    path=unquote(urlparse(urljoin(ORIGIN,url)).path)
    if path in path_map:return path_map[path]
    short=re.search(r'/short-url/([0-9a-zA-Z]+)',path)
    if short and short[1] in short_map:return short_map[short[1]]
    sha=re.search(r'([0-9a-f]{40})(?:[_./]|$)',path)
    return sha_map.get(sha[1]) if sha else None

def candidates():
    urls=set()
    for p in rows:
        soup=BeautifulSoup(p['cooked'] or '','html.parser')
        for node in soup.find_all(['img','video','audio','source']):
            for attr in ('src','poster'):
                if node.get(attr):
                    value=urljoin(ORIGIN,node[attr])
                    if urlparse(value).scheme in ('http','https') and upload_id(value) is None:urls.add(value)
        for node in soup.find_all('a',href=True):
            if 'attachment' in node.get('class',[]) and upload_id(node['href']) is None:urls.add(urljoin(ORIGIN,node['href']))
    return sorted(urls)

def fetch(url):
    try:
        host=urlparse(url).hostname
        assert host and host not in {'localhost','mail.google.com'}, 'not a public anonymous media endpoint'
        for address in socket.getaddrinfo(host,None):
            assert ipaddress.ip_address(address[4][0]).is_global,'non-public address'
        digest=hashlib.sha256(url.encode()).hexdigest()[:24]
        directory=SITE/'assets/media';directory.mkdir(parents=True,exist_ok=True)
        cached=list(directory.glob(digest+'.*'))
        if cached:
            path=next((p for p in cached if p.suffix!='.download'),cached[0]);content=path.read_bytes()
            return {'url':url,'path':str(path.relative_to(SITE)),'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
        with urlopen(Request(url,headers={'User-Agent':'Bokeh-public-static-archive/1.0'}),timeout=12) as response:
            mime=response.headers.get_content_type()
            assert mime.startswith(('image/','video/','audio/')) or 'application/' in mime,'source is not a media/file response'
            content=response.read(20_000_001)
        assert len(content)<=20_000_000,'external media exceeds 20 MB'
        ext=mimetypes.guess_extension(mime) or '.download'
        if ext not in {'.png','.jpg','.jpeg','.gif','.webp','.svg','.avif','.bmp','.mp4','.mov','.webm','.mp3','.ogg','.wav','.pdf','.zip'}:ext='.download'
        path=directory/(digest+ext)
        if ext=='.svg':
            (directory/(digest+'.download')).write_bytes(content)
            xml=ET.fromstring(content)
            for parent in xml.iter():
                for child in list(parent):
                    if child.tag.rsplit('}',1)[-1] in {'script','foreignObject','style'}:parent.remove(child)
                for key,value in list(parent.attrib.items()):
                    if key.rsplit('}',1)[-1].startswith('on') or (key.rsplit('}',1)[-1]=='href' and not value.startswith('#')):del parent.attrib[key]
            content=ET.tostring(xml)
        path.write_bytes(content)
        return {'url':url,'path':str(path.relative_to(SITE)),'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
    except Exception as error:return {'url':url,'error':str(error)}

if __name__=='__main__':
    urls=candidates();print(f'Additional public media candidates: {len(urls)}',flush=True)
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,future in enumerate(as_completed([pool.submit(fetch,u) for u in urls]),1):
            results.append(future.result())
            if i%25==0:print(f'Additional media {i}/{len(urls)}',flush=True)
    (ROOT/'additional-media-report.json').write_text(json.dumps({'files':[r for r in results if 'path' in r],'failures':[r for r in results if 'error' in r]},indent=2))
    print(f'Additional media: {sum("path" in r for r in results)} preserved; {sum("error" in r for r in results)} unavailable',flush=True)
