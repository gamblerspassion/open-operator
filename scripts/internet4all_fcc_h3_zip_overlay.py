#!/usr/bin/env python3
"""Build nationwide ZIP area coverage density estimates from measured 2025 FCC H3 data.
Uses 2020 Census ZCTA boundaries ONLY as a spatial key, not as dated broadband coverage.
One H3 cell is assigned to the ZCTA containing its centroid. Cells may cross boundaries.
"""
import os,glob,csv,json,sqlite3,time,urllib.request,zipfile,gzip
from pathlib import Path
import numpy as np
import h3,shapely
from shapely.geometry import shape
from shapely.strtree import STRtree
import shapefile
D=Path("downloaded"); O=Path("zip_results");O.mkdir(exist_ok=True)
files=list(D.glob("**/fcc_h3_all_*.csv.gz"))+list(D.glob("**/denominators_fcc_h3.csv"))
assert len(files)>=25, "Missing H3 extraction artifacts, found "+str([x.name for x in files])
denom=[p for p in files if p.name.startswith("denominators_")]
assert len(denom)==1,files
url="https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
path=Path("/tmp/cb_2020_us_zcta520_500k.zip")
print("Download census geographic boundary overlay",url,flush=True)
urllib.request.urlretrieve(url,path)
with zipfile.ZipFile(path) as z:z.extractall("/tmp/zcta2020/")
sf=glob.glob("/tmp/zcta2020/*.shp")[0]
reader=shapefile.Reader(sf)
fieldnames=[x[0] for x in reader.fields[1:]]
zcol="ZCTA5CE20" if "ZCTA5CE20" in fieldnames else "GEOID20"
zidx=fieldnames.index(zcol)
geoms=[];zips=[]
for rec in reader.iterShapeRecords():
 try:
  geom=shape(rec.shape.__geo_interface__)
  if not geom.is_empty:
   geoms.append(geom);zips.append(str(rec.record[zidx]).zfill(5))
 except:pass
tree=STRtree(geoms);print("Loaded ZIP boundaries",len(geoms),flush=True)
db=sqlite3.connect("fcc_h3_zcta_map.db")
db.execute("PRAGMA journal_mode=OFF");db.execute("PRAGMA synchronous=OFF")
db.execute("CREATE TABLE cells (geoid TEXT PRIMARY KEY,zcta TEXT,bsls INTEGER)")
def process(batch):
 vals=[]
 valid_idx=[];lat=[];lon=[]
 for i,(geoid,total) in enumerate(batch):
  try:
   la,lo=h3.cell_to_latlng(geoid);valid_idx.append(i);lat.append(la);lon.append(lo)
  except:pass
 matched={}
 if valid_idx:
  pts=shapely.points(np.asarray(lon),np.asarray(lat))
  pairs=tree.query(pts,predicate="intersects")
  for pi,gi in zip(pairs[0],pairs[1]):
   x=valid_idx[int(pi)]
   if x not in matched:matched[x]=zips[int(gi)]
 for i,(gid,total) in enumerate(batch):
  vals.append((gid,matched.get(i),int(total or 0)))
 db.executemany("INSERT OR REPLACE INTO cells VALUES (?,?,?)",vals)
 return sum(1 for z in vals if z[1])
mapped=0;count=0;batch=[]
with open(denom[0],newline="") as f:
 for r in csv.DictReader(f):
  batch.append((r["GEOID"],r["TotalBSLs"]))
  if len(batch)>=25000:
   mapped+=process(batch);count+=len(batch);batch=[]
   if count%250000==0:
    db.commit();print("ZIP GRID",count,"mapped",mapped,flush=True)
 if batch:mapped+=process(batch);count+=len(batch)
db.commit()
print("GRID FINISHED",count,mapped,flush=True)
db.execute("CREATE INDEX idx_cells_zip ON cells(zcta)")
with open(O/"zip_h3_denominators.csv","w",newline="") as f:
 w=csv.writer(f);w.writerow(["zcta","total_bsls","h3_cells"])
 w.writerows(db.execute("SELECT zcta,SUM(bsls),COUNT(*) FROM cells WHERE zcta IS NOT NULL GROUP BY zcta"))
db.execute("CREATE TABLE providers (geoid TEXT,provider TEXT,frn TEXT,tech INTEGER,total INTEGER,served INTEGER,PRIMARY KEY(geoid,provider,frn,tech)) WITHOUT ROWID")
pcount=0
for file in files:
 if file==denom[0]:continue
 print("INGEST",file,flush=True)
 rows=[]
 with gzip.open(file,"rt",newline="") as f:
  for r in csv.DictReader(f):
   rows.append((r["GEOID"],r["ProviderName"],r.get("FRN",""),int(r["Technology"]),int(r["TotalBSLs"]),int(r["ServedBSLs"])))
   if len(rows)>=20000:
    db.executemany("INSERT INTO providers VALUES(?,?,?,?,?,?) ON CONFLICT(geoid,provider,frn,tech) DO UPDATE SET total=MAX(total,excluded.total), served=MAX(served,excluded.served)",rows)
    pcount+=len(rows);rows=[]
  if rows:
   db.executemany("INSERT INTO providers VALUES(?,?,?,?,?) ON CONFLICT(geoid,provider,tech) DO UPDATE SET total=MAX(total,excluded.total), served=MAX(served,excluded.served)",rows)
   pcount+=len(rows)
 db.commit();print("INGESTED",file.name,pcount,flush=True)
db.execute("CREATE INDEX idx_provider_geoid ON providers(geoid)")
with open(O/"national_provider_technology_zcta_estimates.csv","w",newline="") as f:
 w=csv.writer(f);w.writerow(["zcta","provider_as_filed","frn","technology_code","provider_total_bsls","provider_served_bsls","zip_total_bsls","provider_covered_h3_cells","estimated_coverage_pct"])
 sql="""SELECT c.zcta,p.provider,p.frn,p.tech,SUM(p.total),SUM(p.served), COUNT(*),d.den
 FROM providers p JOIN cells c ON p.geoid=c.geoid
 JOIN (SELECT zcta,SUM(bsls) AS den FROM cells WHERE zcta IS NOT NULL GROUP BY zcta) d ON d.zcta=c.zcta
 WHERE c.zcta IS NOT NULL
 GROUP BY c.zcta,p.provider,p.frn,p.tech"""
 for z,n,frn,t,tot,served,ncells,den in db.execute(sql):
  w.writerow([z,n,frn,t,tot,served,den,ncells,round(100*served/den,3) if den else None])
db.commit()
man={"fcc_vintage":"Verify actual Esri publication metadata; source service URL references Dec 2024","as_of":"2026-10-22",
"geography":"H3 resolution 8 cell centroids assigned to 2020 Census ZCTAs",
"denominator_h3_cells":count,"mapped_h3_cells":mapped,"provider_h3_records_ingested":pcount,
"output":"national_provider_technology_zcta_estimates.csv",
"important_limitations":["Coverage percentage is an approximate percent of broadband serviceable locations in a ZCTA, not a USPS delivery ZIP or confirmed qualified retail addresses.",
"Centroid approximation can misallocate BSLs in edge H3 cells.",
"2020 geographic boundaries are only a spatial overlay; coverage counts are the newer FCC data.",
"ProviderName and FRN identify reporting entities; sales brand and commissioned product tiers require independent validation.",
"Within an H3 cell, multiple filer records for the same brand and technology use the MAX to avoid unsupported summing of overlapping locations; this can undercount disjoint footprints.",
"Speed tiers and $150 gross payout eligibility are not encoded by Esri's technology-only table."] }
(O/"methodology.json").write_text(json.dumps(man,indent=2))
print("COMPLETE",json.dumps(man),flush=True)
