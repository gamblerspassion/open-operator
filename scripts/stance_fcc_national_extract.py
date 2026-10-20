#!/usr/bin/env python3
"""Extract all public Esri FCC BDC Dec 2025 provider/state counts; attempt county & block exports in scoped manageable queries."""
import os,csv,json,time,urllib.parse,urllib.request,datetime,traceback
from pathlib import Path
BASE="https://services8.arcgis.com/peDZJliSvYims39Q/ArcGIS/rest/services/FCC_Broadband_Data_Collection_December_2024_View/FeatureServer"
OUT=Path("out"); OUT.mkdir(exist_ok=True)
PAT=["Verizon","Cellco","Frontier","Metronet","Lumos","T-Mobile","Brightspeed","Charter","Spectrum","Windstream","Kinetic","Optimum","Altice","Cincinnati Bell","altafiber","EarthLink"]
SUMMARY=[];FAIL=[]

def get(path,params=None,attempts=4):
    u=BASE+path
    if params:u+="?"+urllib.parse.urlencode(params)
    for i in range(attempts):
        try:
            req=urllib.request.Request(u,headers={"User-Agent":"Stance-FCC-National-Coverage-Research/1.0"})
            with urllib.request.urlopen(req,timeout=100) as r: d=json.load(r)
            if "error" in d:raise RuntimeError(str(d["error"])[:400])
            return d
        except Exception as e:
            print("RETRY",path,str(e)[:220],flush=True)
            if i==attempts-1:raise
            time.sleep(2*(i+1))

def query(layer,params):return get(f"/{layer}/query",dict(params,f="json"))

def export(layer,name,selector,limit_pages=10000):
    info=get(f"/{layer}",{"f":"json"})
    fields=[x["name"] for x in info["fields"]]
    print("FIELDS",layer,name,fields,flush=True)
    matchfields=["OBJECTID","GEOID","ProviderName","FRN","Technology","TotalBSLs","ServedBSLs","UnderservedBSLs","UnservedBSLs"]
    cols=[x for x in matchfields if x in fields]
    assert set(["OBJECTID","GEOID","ProviderName","Technology","TotalBSLs","ServedBSLs"]).issubset(cols),name
    oid=0;count=0;page=0
    dest=OUT/(name+".csv")
    with dest.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        while True:
            # Using OBJECTID keyset avoids pagination instability on large hosted layers.
            where=f"OBJECTID > {oid}"
            if selector:where+=" AND ("+selector+")"
            d=query(layer,{"where":where,"outFields":",".join(cols),"orderByFields":"OBJECTID ASC","resultRecordCount":2000,"returnGeometry":"false"})
            rows=d.get("features",[])
            for x in rows:
                a=x["attributes"];w.writerow({k:a.get(k) for k in cols})
            page+=1;count+=len(rows)
            if rows:
                oid=int(rows[-1]["attributes"]["OBJECTID"])
            print("EXTRACT",name,"page",page,"rows",len(rows),"total",count,"last_id",oid,flush=True)
            if not rows or (len(rows)<2000 and not d.get("exceededTransferLimit")):break
            if page>=limit_pages:raise RuntimeError("page cap reached")
    SUMMARY.append({"layer":layer,"name":name,"rows":count,"columns":cols,"file":dest.name})

def main():
    for layer in [11,10,7,6]:
        try:
            info=get(f"/{layer}",{"f":"json"})
            cols=[f["name"] for f in info.get("fields",[])]
            print("SCHEMA",layer,info.get("name"),cols,flush=True)
        except Exception as e:FAIL.append({"schema_layer":layer,"error":str(e)})
    try:export(11,"all_national_provider_state_2025",None)
    except Exception as e:FAIL.append({"layer":11,"error":str(e)});print("FAILED state",str(e),flush=True)
    # County data for target providers, if available; provider-level counts at smaller geographic scale.
    pred=" OR ".join("ProviderName LIKE '%"+x+"%'" for x in PAT)
    try:export(10,"target_provider_county_2025",pred,limit_pages=10000)
    except Exception as e:FAIL.append({"layer":10,"error":str(e)});print("FAILED county",str(e),flush=True)
    (OUT/"manifest.json").write_text(json.dumps({"source":BASE,"claimed_snapshot":"2025-12-31","extracted":datetime.datetime.now(datetime.timezone.utc).isoformat(),"tables":SUMMARY,"errors":FAIL,"note":"BSLs do not imply ZIP-level availability or commission-qualified plans. Provider state counts may duplicate BSLs across multiple network technologies/FRNs."},indent=2))
    if not SUMMARY:raise RuntimeError("No tables extracted")
if __name__=="__main__":main()
