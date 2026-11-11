"""Exercise both hosting layouts using real archive resolver assets."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

class PreparationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.site = Path(self.directory.name)
        (self.site / 'assets/js').mkdir(parents=True)
        (self.site / 'route-map.json').write_text(json.dumps({'topics': {'42': 'example'}, 'categories': {}}))
        (self.site / 'assets/js/resolve-route.js').write_text((ROOT / 'archive/hosting/resolve-route.js').read_text())
        (self.site / 'assets/js/search-init.js').write_text("new PagefindUI({element:'#search'});")
        (self.site / 'robots.txt').write_text('User-agent: *\nAllow: /\nDisallow: /archive.db\n')
        self.html = '''<!doctype html><html><head><meta name="robots" content="noindex,nofollow"><link href="/assets/css/bokeh.css" rel="stylesheet"></head><body><span class="archive-badge">Read-only preview</span><div class="preview-note">Local archive review · Captured October 28, 2026 · The live forum is unchanged</div><main id="main-content"><a href="/t/example/42/">Topic</a><a href="https://github.com/bokeh/bokeh">GitHub</a><img src="/assets/uploads/image.png"><p>Original post says Read-only preview.</p></main></body></html>'''
        self.html = self.html.replace('<main ', '<a href="attachments/index.html">♧ &nbsp; Attachments</a><main ')
        (self.site / 'archive-report.html').write_text(self.html.replace('&nbsp;', '\u00a0'))
        (self.site / 'attachments').mkdir()
        (self.site / 'attachments/index.html').write_text('Standalone index')
        (self.site / 'assets/uploads').mkdir()
        (self.site / 'assets/uploads/image.png').write_bytes(b'preserved attachment bytes')
        (self.site / 'index.html').write_text(self.html)
        alias = self.site / 't/example/42/2'
        alias.mkdir(parents=True)
        (alias / 'index.html').write_text('<html><head><meta name="robots" content="noindex"><meta http-equiv="refresh" content="0;url=/t/example/42/#post-2"></head></html>')

    def prepare(self, *args, check=True):
        return subprocess.run([sys.executable, str(ROOT / 'prepare.py'), str(self.site), *args],
                              check=check, capture_output=True, text=True)

    def test_production_root_metadata_links_and_post_redirects(self):
        self.prepare('--base-path', '/', '--production')
        self.assertFalse((self.site / 'attachments').exists())
        self.assertEqual((self.site / 'assets/uploads/image.png').read_bytes(), b'preserved attachment bytes')
        html = (self.site / 'index.html').read_text()
        self.assertNotIn('♧ &nbsp; Attachments', html)
        self.assertNotIn('attachments/index.html', (self.site / 'archive-report.html').read_text())
        self.assertNotIn('content="noindex,nofollow"', html)
        self.assertIn('class="archive-badge">Read-only archive</span>', html)
        self.assertIn('class="preview-note">Archived discussions · Captured October 28, 2026</div>', html)
        self.assertIn('href="/t/example/42/"', html)
        self.assertIn('src="/assets/uploads/image.png"', html)
        self.assertIn('Original post says Read-only preview.', html)
        self.assertIn('href="https://github.com/bokeh/bokeh"', html)
        redirect = (self.site / 't/example/42/2/index.html').read_text()
        self.assertIn('content="noindex"', redirect)
        self.assertIn('content="0;url=/t/example/42/#post-2"', redirect)
        self.assertIn('const archiveBase="";', (self.site / 'assets/js/resolve-route.js').read_text())
        self.assertIn('baseUrl:"/",bundlePath:"/pagefind/"', (self.site / 'assets/js/search-init.js').read_text())
        self.assertFalse((self.site / 'CNAME').exists())

    def test_review_prefix_and_noindex_remain(self):
        self.prepare('--base-path', '/discourse.bokeh.org/')
        self.assertFalse((self.site / 'attachments').exists())
        self.assertEqual((self.site / 'assets/uploads/image.png').read_bytes(), b'preserved attachment bytes')
        html = (self.site / 'index.html').read_text()
        self.assertNotIn('♧ &nbsp; Attachments', html)
        self.assertNotIn('attachments/index.html', (self.site / 'archive-report.html').read_text())
        self.assertIn('content="noindex,nofollow"', html)
        self.assertIn('href="/discourse.bokeh.org/t/example/42/"', html)
        self.assertIn('src="/discourse.bokeh.org/assets/uploads/image.png"', html)
        self.assertIn('class="archive-badge">Read-only archive</span>', html)
        self.assertIn('baseUrl:"/discourse.bokeh.org/"', (self.site / 'assets/js/search-init.js').read_text())

    def test_sitemap_selects_public_content_and_preserves_pagination(self):
        routes = json.loads((self.site / 'route-map.json').read_text())
        routes['categories'] = {'5': 'tips&tricks'}
        (self.site / 'route-map.json').write_text(json.dumps(routes))
        pages = {
            't/example/42/index.html': self.html,
            't/example/42/page-2.html': self.html,
            't/example/42/page-10.html': self.html,
            't/example/42/page-100.html': self.html,
            't/example/42/page-3.html': '<meta name="robots" content="NOINDEX, follow">',
            't/example/42/page-4.html': '<meta name="googlebot" content="none">',
            't/example/42/page-5.html': '<meta http-equiv="refresh" content="0;url=/">',
            't/private/99/index.html': self.html,
            't/42/index.html': self.html,
            'c/tips&tricks/5/index.html': self.html,
            'c/tips&tricks/5/page-2.html': self.html,
            'c/private/6/index.html': self.html,
            'latest/index.html': self.html,
            'latest/page-2.html': self.html,
            'top/index.html': self.html,
            'top/replies/index.html': self.html,
            'top/views/index.html': self.html,
            'search.html': self.html,
            '404.html': self.html,
            'uploads/short-url/file/index.html': self.html,
        }
        for name, content in pages.items():
            path = self.site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.prepare('--base-path', '/', '--production')
        sitemap = self.site / 'sitemap.xml'
        root = ET.parse(sitemap).getroot()
        self.assertEqual(root.tag, '{http://www.sitemaps.org/schemas/sitemap/0.9}urlset')
        urls = [element.text for element in root.findall('{*}url/{*}loc')]
        paths = ['', 'archive-report.html', 't/example/42/', 't/example/42/page-2.html',
                 't/example/42/page-10.html', 't/example/42/page-100.html',
                 'c/tips%26tricks/5/', 'c/tips%26tricks/5/page-2.html',
                 'latest/', 'latest/page-2.html', 'top/', 'top/replies/', 'top/views/']
        self.assertEqual(urls, sorted('https://discourse.bokeh.org/' + path for path in paths))
        robots = (self.site / 'robots.txt').read_text()
        self.assertIn('Disallow: /archive.db\n', robots)
        self.assertEqual(robots.count('Sitemap: https://discourse.bokeh.org/sitemap.xml'), 1)

    def test_review_removes_stale_sitemap_and_discovery(self):
        (self.site / 'sitemap.xml').write_text('stale production sitemap')
        with (self.site / 'robots.txt').open('a') as robots:
            robots.write('Sitemap: https://discourse.bokeh.org/sitemap.xml\n')
        self.prepare('--base-path', '/review')
        self.assertFalse((self.site / 'sitemap.xml').exists())
        self.assertNotIn('Sitemap:', (self.site / 'robots.txt').read_text())

    def test_production_rejects_project_prefix(self):
        result = self.prepare('--base-path', '/discourse.bokeh.org/', '--production', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.site / 'index.html').read_text(), self.html)

if __name__ == '__main__': unittest.main()
