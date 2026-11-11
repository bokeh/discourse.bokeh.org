"""Prepare the existing archive for a Pages review or the final domain root."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote
from xml.etree import ElementTree as ET

PRODUCTION_URL = "https://discourse.bokeh.org"
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"

class ProjectHTML(HTMLParser):
    def __init__(self, base, production=False):
        super().__init__(convert_charrefs=False)
        self.base = base
        self.production = production
        self.output = []
        self.indexable = True

    def start(self, tag, attrs):
        raw = self.get_starttag_text()
        attributes = dict(attrs)
        if (self.production and tag == 'meta' and attributes.get('name') == 'robots'
                and attributes.get('content') == 'noindex,nofollow'):
            return
        if tag == 'meta':
            name = attributes.get('name', '').lower()
            directives = re.split(r'[,\s]+', attributes.get('content', '').lower())
            if (name in ('robots', 'googlebot') and {'noindex', 'none'} & set(directives)
                    or attributes.get('http-equiv', '').lower() == 'refresh'):
                self.indexable = False
        raw = re.sub(r'''(\b(?:href|src|poster|action)\s*=\s*["'])/(?!/)''',
                     lambda match: match[1] + self.base + '/', raw)
        if tag == 'meta':
            raw = raw.replace('0;url=/', '0;url=' + self.base + '/')
        self.output.append(raw)

    def handle_starttag(self, tag, attrs): self.start(tag, attrs)
    def handle_startendtag(self, tag, attrs): self.start(tag, attrs)
    def handle_endtag(self, tag): self.output.append(f'</{tag}>')
    def handle_data(self, data): self.output.append(data)
    def handle_entityref(self, name): self.output.append(f'&{name};')
    def handle_charref(self, name): self.output.append(f'&#{name};')
    def handle_comment(self, data): self.output.append(f'<!--{data}-->')
    def handle_decl(self, decl): self.output.append(f'<!{decl}>')

def sitemap_directories(routes):
    """Select content directories from the public route map and archive listings."""
    directories = {Path('.'), Path('latest'), Path('top'),
                   Path('top/replies'), Path('top/views')}
    for kind, prefix in (('topics', 't'), ('categories', 'c')):
        for identifier, slug in routes[kind].items():
            assert identifier.isdigit() and slug and '/' not in slug and slug not in ('.', '..')
            directories.add(Path(prefix) / slug / identifier)
    return directories

def write_sitemap(site, urls):
    ET.register_namespace('', SITEMAP_NAMESPACE)
    root = ET.Element(f'{{{SITEMAP_NAMESPACE}}}urlset')
    for url in sorted(urls):
        entry = ET.SubElement(root, f'{{{SITEMAP_NAMESPACE}}}url')
        ET.SubElement(entry, f'{{{SITEMAP_NAMESPACE}}}loc').text = url
    assert 0 < len(urls) <= 50_000, 'Sitemap requires between 1 and 50,000 URLs'
    ET.indent(root, space='  ')
    content = ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n'
    assert len(content) <= 50 * 1024 * 1024, 'Sitemap exceeds 50 MB'
    (site / 'sitemap.xml').write_bytes(content)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('site', type=Path)
    parser.add_argument('--base-path', required=True)
    parser.add_argument('--production', action='store_true', help='Prepare an indexable domain-root archive without review labels')
    args = parser.parse_args()
    base = '/' + args.base_path.strip('/') if args.base_path.strip('/') else ''
    assert not base or re.fullmatch(r'/[A-Za-z0-9._-]+', base)
    assert not args.production or not base, 'Production is served at the domain root'
    site = args.site
    assert not (site / 'CNAME').exists(), 'Preparation must not configure a custom domain'
    routes = json.loads((site / 'route-map.json').read_text())
    assert not any(slug.isdigit() for slug in routes['topics'].values())
    # Numeric aliases use the 404 resolver and then the retained canonical post URL.
    # Removing duplicate alias directories keeps the Pages artifact comfortably small.
    for topic_id in routes['topics']:
        alias = site / 't' / topic_id
        if alias.is_dir(): shutil.rmtree(alias)
    # The frozen snapshot includes a standalone media index. Preserve only post links.
    attachment_index = site / "attachments"
    if attachment_index.is_dir(): shutil.rmtree(attachment_index)
    directories = sitemap_directories(routes)
    sitemap_urls = set()
    count = 0
    for path in site.rglob('*.html'):
        if not path.is_file(): continue
        document = ProjectHTML(base, args.production)
        document.feed(path.read_text())
        document.close()
        result = ''.join(document.output)
        result = re.sub(r'<a href="[^"]*attachments/index\.html">♧ (?:&nbsp;|\u00a0) Attachments</a>', '', result)
        result = result.replace('Local archive review ·', 'Archive review ·')
        result = result.replace(' · The live forum is unchanged', '')
        result = result.replace(' The live forum has not been modified.', '')
        result = result.replace('<span class="archive-badge">Read-only preview</span>',
                                '<span class="archive-badge">Read-only archive</span>')
        result = result.replace('<div class="preview-note">Archive review ·',
                                '<div class="preview-note">Archived discussions ·')
        relative = path.relative_to(site)
        canonical_page = (relative.parent in directories
                          and re.fullmatch(r'index\.html|page-(?:[2-9]|[1-9][0-9]+)\.html', relative.name))
        if args.production and document.indexable and (canonical_page or relative == Path('archive-report.html')):
            canonical_path = relative.as_posix()
            if relative.name == 'index.html':
                canonical_path = canonical_path.removesuffix('index.html')
            sitemap_urls.add(PRODUCTION_URL + '/' + quote(canonical_path, safe='/'))
        path.write_text(result)
        count += 1
    resolver = site / 'assets/js/resolve-route.js'
    script = resolver.read_text()
    script = script.replace("fetch('/route-map.json')", "fetch(archiveBase+'/route-map.json')")
    script = script.replace("location.pathname.split('/')", "location.pathname.slice(archiveBase.length).split('/')")
    script = script.replace("if(target&&target.replace", "if(target)target=archiveBase+target;if(target&&target.replace")
    resolver.write_text('const archiveBase=' + json.dumps(base) + ';' + script)
    search = site / 'assets/js/search-init.js'
    options = 'baseUrl:' + json.dumps(base + '/') + ',bundlePath:' + json.dumps(base + '/pagefind/') + ','
    search.write_text(search.read_text().replace('new PagefindUI({', 'new PagefindUI({' + options))
    robots = site / 'robots.txt'
    lines = [line for line in robots.read_text().splitlines()
             if not line.lstrip().lower().startswith('sitemap:')]
    if args.production:
        write_sitemap(site, sitemap_urls)
        lines.extend(['', f'Sitemap: {PRODUCTION_URL}/sitemap.xml'])
    else:
        (site / 'sitemap.xml').unlink(missing_ok=True)
    robots.write_text('\n'.join(lines).rstrip() + '\n')
    size = sum(p.stat().st_size for p in site.rglob('*') if p.is_file())
    assert size < 1_000_000_000, f'Published site exceeds 1 GB: {size}'
    print(f'Prepared {count:,} HTML pages at {base}/. Published size: {size:,} bytes.', flush=True)

if __name__ == '__main__': main()
