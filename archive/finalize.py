"""Restore hosting helpers after rendering the frozen snapshot."""
import json
from pathlib import Path
import shutil
from chronicon.storage.database import ArchiveDatabase

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'site'
db=ArchiveDatabase(ROOT/'archive.sqlite')
routes={'topics':{str(t.id):t.slug for t in db.get_all_topics()},
        'categories':{str(c.id):c.slug for c in db.get_all_categories()}}
db.close()
(SITE/'route-map.json').write_text(json.dumps(routes,separators=(',',':')))
shutil.copy(ROOT/'hosting/404.html',SITE/'404.html')
shutil.copy(ROOT/'hosting/resolve-route.js',SITE/'assets/js/resolve-route.js')
(SITE/'assets/js/search-init.js').write_text("const archiveSearch=new PagefindUI({element:'#search',showSubResults:true,showImages:false,pageSize:10});const query=new URLSearchParams(location.search).get('q');if(query)archiveSearch.triggerSearch(query);")
