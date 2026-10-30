# Bokeh Discourse archive review

Review the static public archive at https://bokeh.github.io/discourse.bokeh.org/.

This is a review deployment. The live forum and `discourse.bokeh.org` remain unchanged. This repository has no custom domain or `CNAME` file. Search engines are asked not to index the review copy.

The October 28, 2026 snapshot contains 7,149 topics and 35,823 public posts from Showcase, Announcements, and Community Support. It preserves 5,357 public uploads and avatars, plus 583 additional media files. Thirty-eight unavailable historical external media sources are documented in the site's capture report. The support banner points to GitHub Discussions.

The frozen deployable snapshot is stored as a Release asset to avoid committing nearly 1 GB of generated files. `snapshot.json` pins its SHA-256 checksum. The Pages workflow verifies and extracts it, then `prepare.py` adjusts domain-root links, search, and historical URL fallback for the review project's path.

To redeploy this snapshot, run **Actions → Deploy archive review → Run workflow**. Replacing the snapshot requires a new Release asset and an updated `snapshot.json` checksum.

The static snapshot is a public reference archive. It is not a restorable Discourse database backup. Historical author attribution is retained. Private messages, private categories, deleted/hidden posts, staff whispers, and account configuration are excluded.
