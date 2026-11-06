"""Prepare the existing archive for a Pages review or the final domain root."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil

class ProjectHTML(HTMLParser):
    def __init__(self, base, production=False):
        super().__init__(convert_charrefs=False)
        self.base = base
        self.production = production
        self.output = []

    def start(self, tag, attrs):
        raw = self.get_starttag_text()
        attributes = dict(attrs)
        if (self.production and tag == 'meta' and attributes.get('name') == 'robots'
                and attributes.get('content') == 'noindex,nofollow'):
            return
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
    count = 0
    for path in site.rglob('*.html'):
        if not path.is_file(): continue
        document = ProjectHTML(base, args.production)
        document.feed(path.read_text())
        document.close()
        result = ''.join(document.output)
        result = re.sub(r'<a href="[^"]*attachments/index\.html">♧ &nbsp; Attachments</a>', '', result)
        result = result.replace('Local archive review ·', 'Archive review ·')
        result = result.replace(' · The live forum is unchanged', '')
        result = result.replace(' The live forum has not been modified.', '')
        result = result.replace('<span class="archive-badge">Read-only preview</span>',
                                '<span class="archive-badge">Read-only archive</span>')
        result = result.replace('<div class="preview-note">Archive review ·',
                                '<div class="preview-note">Archived discussions ·')
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
    size = sum(p.stat().st_size for p in site.rglob('*') if p.is_file())
    assert size < 1_000_000_000, f'Published site exceeds 1 GB: {size}'
    print(f'Prepared {count:,} HTML pages at {base}/. Published size: {size:,} bytes.', flush=True)

if __name__ == '__main__': main()
