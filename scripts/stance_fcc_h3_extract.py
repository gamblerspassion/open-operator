#!/usr/bin/env python3
"""National FCC H3 provider extraction from Esri ArcGIS feature service.
One group per isolated GitHub Actions job. Read-only external requests."""
import os,csv,json,sys,time,urllib.parse,urllib.request,datetime,pathlib
BASE="https://services8.arcgis.com/peDZJliSvYims39Q/ArcGIS/rest/services/FCC_Broadband_Data_Collection_December_2024_View/FeatureServer"
GROUPS={
"verizon":["Verizon"],
"tmobile":["T-Mobile"],
"spectrum":["Spectrum"],
"frontier_brightspeed":["Frontier","Brightspeed"],
"metronet_lumos":["Metronet Holdings","lumos","Lumos"],
"optimum_altafiber":["Optimum","altafiber Network Solutions","altafiber Extended Territories"],
"windstream":["Windstream%"],
"denominators":[]
}
arg=sys.argv[1]
assert arg in GROUPS
out=pathlib.Path("out");out.mkdir(exist_ok=True)
layer=5 if arg=="denominators" else 6
basecols=["OBJECTID","GEOID","TotalBSLs","ServedBSLs"] if layer==5 else ["OBJECTID","GEOID","ProviderName","FRN","Technology","TotalBSLs","ServedBSLs"]
state=datetime.datetime.now(datetime.timezone.utc)
def fetch(params):
 u=BASE+"/"+str(layer)+"/query?"+urllib.parse.urlencode(dict(params,f="json"))
 for retry in range(5):
  try:
   req=urllib.request.Request(u,headers={"User-Agent":"Stance FCC data extraction / 2026-10"})
   with urllib.request.urlopen(req,timeout=120) as r: d=json.load(r)
   if "error" in d:raise ValueError(str(d["error"])[:500])
   return d
  except Exception as e:
   print("RETRY",arg,retry,str(e)[:150],flush=True)
   if retry==4:raise
   time.sleep((retry+1)*2)
def iterate(where,writer):
 oid=0;count=0;pages=0
 while True:
  qwhere=f"OBJECTID>{oid}" + (" AND ("+where+")" if where else "")
  d=fetch({"where":qwhere,"outFields":",".join(basecols),"returnGeometry":"false",
   "orderByFields":"OBJECTID ASC","resultRecordCount":2000})
  records=d.get("features",[])
  if not records:break
  for row in records:writer.writerow({k:row["attributes"].get(k) for k in basecols})
  oid=int(records[-1]["attributes"]["OBJECTID"]);count+=len(records);pages+=1
  if pages%50==0:print("PROGRESS",arg,where,pages,count,oid,flush=True)
  if len(records)<2000 and not d.get("exceededTransferLimit"):break
  if pages>16000:raise RuntimeError("page safety cap")
 return count,pages
if arg=="windstream":
 where="ProviderName LIKE 'Windstream%'"
elif arg!="denominators":
 where=" OR ".join("ProviderName = '"+name.replace("'","''") + "'" for name in GROUPS[arg])
else:where=""
fname=out/(arg+"_fcc_h3.csv")
with fname.open("w",newline="",encoding="utf-8") as f:
 w=csv.DictWriter(f,fieldnames=basecols);w.writeheader();count,pages=iterate(where,w)
meta={"group":arg,"layer":layer,"records":count,"pages":pages,"source":BASE,
  "snapshot":"2025-12-31 (check ArcGIS item metadata)","timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "note":"H3 is not ZIP. Same-provider repeated rows can overlap serviceable locations. Sum carefully by technology/FRN."}
(out/(arg+"_manifest.json")).write_text(json.dumps(meta,indent=2))
print("DONE",json.dumps(meta),flush=True)
