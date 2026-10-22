#!/usr/bin/env python3
"""National all-provider H3 extraction from the successfully tested Esri FCC BDC.
Deterministic OBJECTID ranges; parallel shards, one GitHub job each.
Uses the EXACT source/layer and pagination pattern verified Oct 20.
Outputs gzipped CSV plus a completeness manifest per shard. No guessed IDs.
"""
import argparse,csv,datetime,gzip,json,math,pathlib,time,urllib.parse,urllib.request
BASE="https://services8.arcgis.com/peDZJliSvYims39Q/ArcGIS/rest/services/FCC_Broadband_Data_Collection_December_2024_View/FeatureServer"
p=argparse.ArgumentParser()
p.add_argument("--shard",type=int,required=True);p.add_argument("--shards",type=int,default=24)
p.add_argument("--max-pages",type=int,default=15000); args=p.parse_args()
assert args.shards>0 and 0<=args.shard<args.shards
OUTPUT=pathlib.Path("out");OUTPUT.mkdir(exist_ok=True)
FIELDS=["OBJECTID","GEOID","ProviderName","FRN","Technology","TotalBSLs","ServedBSLs","UnderservedBSLs","UnservedBSLs"]
def get(layer,params=None):
 url=BASE+"/"+str(layer)
 if params:url+="/query?"+urllib.parse.urlencode(dict(params,f="json"))
 else:url+="?f=json"
 for attempt in range(6):
  try:
   r=urllib.request.Request(url,headers={"User-Agent":"Internet4ALL FCC H3 national analysis / Oct 2026"})
   with urllib.request.urlopen(r,timeout=120) as resp:d=json.load(resp)
   if "error" in d:raise RuntimeError(str(d["error"])[:500])
   return d
  except Exception as e:
   print("RETRY",args.shard,attempt,str(e)[:120],flush=True)
   if attempt==5:raise
   time.sleep((attempt+1)*3)
schema=get(6)
fields=[x["name"] for x in schema["fields"]]
cols=[x for x in FIELDS if x in fields]
assert all(x in cols for x in ["OBJECTID","GEOID","ProviderName","FRN","Technology","TotalBSLs","ServedBSLs"]),cols
maxrow=get(6,{"where":"1=1","outFields":"OBJECTID","orderByFields":"OBJECTID DESC","resultRecordCount":1,"returnGeometry":"false"}).get("features",[])
if not maxrow:raise RuntimeError("Unable to obtain max source OBJECTID")
maximum=int(maxrow[0]["attributes"]["OBJECTID"])
boundary=math.ceil(maximum/args.shards)
lo=boundary*args.shard;hi=min(maximum,boundary*(args.shard+1))
selector=f"OBJECTID>{lo} AND OBJECTID<={hi}"
expected=get(6,{"where":selector,"returnCountOnly":"true"}).get("count")
if not isinstance(expected,int) or expected<0:raise RuntimeError("Bad source row count")
path=OUTPUT/("fcc_h3_all_%02d_of_%02d.csv.gz"%(args.shard,args.shards))
seen=0;pages=0;cursor=lo
with gzip.open(path,"wt",encoding="utf-8",newline="",compresslevel=4) as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 while cursor<hi:
  where=f"OBJECTID>{cursor} AND OBJECTID<={hi}"
  response=get(6,{"where":where,"outFields":",".join(cols),"orderByFields":"OBJECTID ASC","returnGeometry":"false","resultRecordCount":2000})
  rows=response.get("features",[])
  if not rows:break
  for feature in rows:
   a=feature["attributes"];oid=int(a["OBJECTID"])
   if oid<=cursor or oid>hi:raise RuntimeError(f"Out-of-order or outside shard: {oid} after {cursor}")
   cursor=oid
   w.writerow({k:a.get(k) for k in cols});seen+=1
  pages+=1
  if pages%100==0:print("PROGRESS",args.shard,seen,expected,"cursor",cursor,flush=True)
  if pages>=args.max_pages:raise RuntimeError("Safety page limit hit; shard incomplete")
  if len(rows)<2000 and not response.get("exceededTransferLimit"):break
if seen!=expected:raise RuntimeError(f"Incomplete shard {args.shard}: {seen} vs {expected}")
manifest={"shard":args.shard,"shards":args.shards,"lower_oid_exclusive":lo,"upper_oid_inclusive":hi,"max_oid":maximum,"expected_count":expected,"actual_count":seen,"pages":pages,"source":BASE,"layer":6,"columns":cols,"completed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"complete":True}
(OUTPUT/("fcc_h3_%02d_manifest.json"%args.shard)).write_text(json.dumps(manifest,indent=2)+"\n")
print("SUCCESS",json.dumps(manifest),flush=True)
