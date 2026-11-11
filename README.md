# Bokeh Discourse archive

[Browse the archive](https://discourse.bokeh.org/).

The live forum is retained in read-only mode during cutover. The GitHub Pages deployment serves the static archive at the domain root.

The October 28, 2026 public snapshot contains 7,149 topics and 35,823 posts from Showcase, Announcements, and Community Support. It preserves 5,357 public uploads and avatars, plus 583 additional media files. Thirty-eight unavailable historical external media sources are documented in the capture report.

## Rebuild on GitHub

Open **Actions → Rebuild archive from sources → Run workflow**. A fresh runner installs the pinned build dependencies, downloads the checksum-pinned capture inputs, imports the public JSON into a new SQLite database, sanitizes and renders all posts, builds Pagefind search, and validates links, post counts, and file checksums.

The completed run provides a **rebuilt-archive** artifact containing the regenerated website ZIP and validation reports. It does not deploy or modify the current Pages review site. Download the artifact within seven days or run the workflow again.

No local worktree, existing database, droplet credentials, production connection, or original media host is required. Network access is blocked inside the Python import, normalization, rendering, and validation stages. Installing dependencies and downloading capture inputs still requires the internet.

## Where the inputs live

- `archive/` contains the build scripts, Bokeh theme, templates, hosting helpers, validation, packaging, and read-only capture SQL.
- `vendor/chronicon/` preserves the exact renderer package sources and upstream Unlicense. Runtime dependency versions are pinned in `requirements-build.txt`. Pagefind is pinned to 1.5.2.
- [`public-source-2026-10-28.zip`](https://github.com/bokeh/discourse.bokeh.org/releases/download/review-2026-10-30/public-source-2026-10-28.zip) contains the selected public JSON export, checksum reconciliation metadata, capture counts, and frozen media manifests. `source-snapshot.json` pins its checksum.
- [`bokeh-discourse-archive.zip`](https://github.com/bokeh/discourse.bokeh.org/releases/download/review-2026-10-30/bokeh-discourse-archive.zip) preserves all captured media alongside the original static output. The rebuild extracts only its `assets/` files. It regenerates HTML, the database, category pages, URL aliases, and search from the JSON. `snapshot.json` pins this ZIP's checksum.

The large data files are Release assets so they do not bloat Git history. Neither asset depends on this chat or the original local checkout. Keep both pinned assets when maintaining the repository.

Only selected public categories, visible public posts, and public media were captured. Private messages, private categories, deleted/hidden posts, staff whispers, account email fields and account configuration are excluded. Public text retains its original author attribution. This capture is a public reference archive, not a restorable production Discourse backup.

## Rebuild locally

Use Python 3.13 and Node.js 24 with npm available. From a fresh clone:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-build.txt
python -u rebuild.py
python -m http.server 8769 --bind 127.0.0.1 --directory archive/site
```

Open http://127.0.0.1:8769/. The generated ZIP is `archive/bokeh-discourse-archive.zip`. Generated output is ignored by Git. The rebuilt site has the same captured content and routes. ZIP timestamps, generation metadata, and file ordering need not be byte-identical.

## Publish a snapshot

**Actions → Deploy Discourse archive → Run workflow** deploys the pinned rendered ZIP. The `prepare.py` adapter prepares domain-root links, search, and historical URL fallback. Changes to the source builder do not automatically replace the published snapshot.

Publishing a rebuilt snapshot is a separate step. Preserve it as a new Release asset and update `snapshot.json` after reviewing the output.

## Production hosting

The archive is prepared for `https://discourse.bokeh.org/` at the domain root. The normal Pages workflow validates all public posts, links, and preserved media before deploying. Content pages are indexable. Redirect aliases and the 404 page retain their intentional `noindex` metadata.

Production preparation generates a deterministic root-level `sitemap.xml` with absolute HTTPS URLs and adds its discovery URL to `robots.txt`. It includes public topic and category routes, their rendered pagination, archive listings, and the capture report. Directory indexes use trailing-slash URLs. Redirect aliases, search, fallback pages, attachments, and pages retaining `noindex` metadata are excluded. Review preparation removes the sitemap and its discovery directive.

In **Actions → Deploy Discourse archive → Run workflow**, select **production** to create a downloadable `production-archive` package without deploying. This uses the same preparation and validation as a deployment. Artifacts are retained for 14 days.

The source snapshot remains frozen. DNS and the Pages custom-domain setting are managed separately from workflow runs. Attachment files remain available from their original posts. There is no standalone attachment index.
