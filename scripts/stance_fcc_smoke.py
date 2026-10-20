#!/usr/bin/env python3
# Read-only smoke test: query five actual Esri nationwide state-provider records.
import urllib.parse,urllib.request,json,sys,datetime,os
BASE="https://services8.arcgis.com/peDZJliSvYims39Q/ArcGIS/rest/services/FCC_Broadband_Data_Collection_December_2024_View/FeatureServer"
def get(path,p=None):
    url=BASE+path+(("?"+urllib.parse.urlencode(p)) if p else "")
    req=urllib.request.Request(url,headers={"User-Agent":"Stance-FCC-Research/1.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        return json.load(r)
info=get("/11",{"f":"json"})
fields=[x["name"] for x in info.get("fields",[])]
assert set(["OBJECTID","GEOID","ProviderName","FRN","Technology","TotalBSLs","ServedBSLs"]).issubset(fields),str(fields)
result=get("/11/query",{"where":"1=1","outFields":"OBJECTID,GEOID,ProviderName,Technology,TotalBSLs,ServedBSLs","returnGeometry":"false","resultRecordCount":"5","f":"json"})
assert result.get("features"),json.dumps(result)[:2000]
os.makedirs("out",exist_ok=True)
with open("out/verified_query.json","w") as f:json.dump({"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"source":BASE,"fields":fields,"sample":result["features"]},f,indent=2)
print("SUCCESS: returned",len(result["features"]),"state provider records")
for r in result["features"]: print(r["attributes"])
