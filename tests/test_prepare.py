"""Exercise both hosting layouts using real archive resolver assets."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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

    def test_production_rejects_project_prefix(self):
        result = self.prepare('--base-path', '/discourse.bokeh.org/', '--production', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.site / 'index.html').read_text(), self.html)

if __name__ == '__main__': unittest.main()
