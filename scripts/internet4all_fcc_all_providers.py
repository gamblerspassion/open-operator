#!/usr/bin/env python3
"""Internet 4 ALL -- use the ORIGINAL WORKING Stance FCC/Esri extraction method.

Source and layer IDs match the successfully executed Oct 20 2026 extraction:
  layer 11: all-provider state offerings
  layer 10: all-provider county offerings
  layer 6:  H3 provider records (later partitioned extraction)
  layer 5:  H3 broadband serviceable location denominators
Always use OBJECTID keyset pagination; DO NOT use ArcGIS offset pagination.
Output is reporting-entity coverage, NOT customer order or address eligibility.
"""
import argparse,csv,datetime,json,pathlib,time,urllib.parse,urllib.request

BASE="https://services8.arcgis.com/peDZJliSvYims39Q/ArcGIS/rest/services/FCC_Broadband_Data_Collection_December_2024_View/FeatureServer"
FIELDS=["OBJECTID","GEOID","ProviderName","FRN","Technology","TotalBSLs","ServedBSLs","UnderservedBSLs","UnservedBSLs"]
parser=argparse.ArgumentParser()
parser.add_argument("--level",choices=["state","county"],required=True)
parser.add_argument("--max-pages",type=int,default=30000)
args=parser.parse_args()
layer={"state":11,"county":10}[args.level]
out=pathlib.Path("out");out.mkdir(exist_ok=True)
def get(url,params=None):
 if params:url+="?"+urllib.parse.urlencode(params)
 for attempt in range(5):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Internet4ALL National FCC/Esri extraction/2026-10"}),timeout=110) as response:
    d=json.load(response)
   if "error" in d:raise RuntimeError(str(d["error"]))
   return d
  except Exception as e:
   print("RETRY",args.level,attempt,str(e)[:200],flush=True)
   if attempt==4:raise
   time.sleep(2*(attempt+1))
meta=get(BASE+"/"+str(layer),{"f":"json"})
available={f["name"] for f in meta.get("fields",[])}
required={"OBJECTID","GEOID","ProviderName","Technology","TotalBSLs","ServedBSLs"}
if not required.issubset(available):raise RuntimeError("Unexpected layer schema "+str(sorted(available)))
cols=[f for f in FIELDS if f in available]
count_obj=get(BASE+"/"+str(layer)+"/query",{"f":"json","where":"1=1","returnCountOnly":"true"})
expected=count_obj.get("count")
assert isinstance(expected,int) and expected>=0,expected
print("SOURCE",BASE,"LAYER",layer,"FIELDS",cols,"COUNT",expected,flush=True)
output=out/("fcc_all_providers_"+args.level+"_2025.csv")
seen=set(); oid=0;rows=0; pages=0; names=set();frns=set()
with output.open("w",encoding="utf-8",newline="") as f:
 writer=csv.DictWriter(f,fieldnames=cols)
 writer.writeheader()
 while True:
  response=get(BASE+"/"+str(layer)+"/query",{"f":"json","where":f"OBJECTID>{oid}","outFields":",".join(cols),"orderByFields":"OBJECTID ASC","returnGeometry":"false","resultRecordCount":2000})
  features=response.get("features",[])
  if not features:break
  for feature in features:
   a=feature["attributes"]; new=int(a["OBJECTID"])
   if new<=oid:raise RuntimeError("Nonincreasing OBJECTID: "+str(new))
   oid=new
   writer.writerow({k:a.get(k) for k in cols})
   rows+=1
   if a.get("ProviderName"):names.add(str(a["ProviderName"]))
   if a.get("FRN") is not None:frns.add(str(a["FRN"]))
  pages+=1
  if pages%25==0:print("PROGRESS",args.level,pages,rows,"last_oid",oid,flush=True)
  if pages>=args.max_pages:raise RuntimeError("Safety page cap; partial export, not complete")
  if len(features)<2000 and not response.get("exceededTransferLimit"):break
if rows!=expected:raise RuntimeError(f"Incomplete {args.level} data: downloaded {rows}, expected {expected}")
manifest={"source_url":BASE,"source_label":"FCC broadband data collection hosted by Esri; verify publication/vintage","level":args.level,"layer_id":layer,"source_layer_name":meta.get("name"),"records":rows,"expected":expected,"pages":pages,"unique_provider_names":len(names),"unique_frns":len(frns),"columns":cols,"completed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"complete":True,"limitations":"Availability from FCC reporting entities, not verified exact-address qualification"}
(out/("fcc_"+args.level+"_manifest.json")).write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8")
print("SUCCESS",json.dumps(manifest),flush=True)
