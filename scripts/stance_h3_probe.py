#!/usr/bin/env python3
import urllib.parse,urllib.request,json,time
BASE="https://services8.arcgis.com/peDZJliSvYims39Q/ArcGIS/rest/services/FCC_Broadband_Data_Collection_December_2024_View/FeatureServer"
NAMES=["Spectrum","Verizon","T-Mobile","Metronet Holdings","lumos","Lumos","Frontier","Brightspeed","Optimum","altafiber Network Solutions","altafiber Extended Territories"]
def get(path,p):
 u=BASE+path+"?"+urllib.parse.urlencode(dict(p,f="json"))
 for i in range(3):
  try:
   with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Stance FCC exploratory research"}),timeout=90) as r: d=json.load(r)
   if "error" in d: raise Exception(d["error"])
   return d
  except Exception as e:
   print("RETRY",str(e)[:200],flush=True);time.sleep(i+1)
 raise Exception("request failed")
for layer in [5,6,7]:
 info=get(f"/{layer}",{})
 print("LAYER",layer,"name",info.get("name"),"maxRecordCount",info.get("maxRecordCount"),"fields",[x["name"] for x in info.get("fields",[])],flush=True)
 if layer in [5,6]:
  print("COUNT_ALL",layer,get(f"/{layer}/query",{"where":"1=1","returnCountOnly":"true"}).get("count"),flush=True)
  print("SAMPLE",layer,get(f"/{layer}/query",{"where":"1=1","outFields":"*","returnGeometry":"false","resultRecordCount":"2"}).get("features",[])[:2],flush=True)
for name in NAMES:
 for layer in [6,7]:
  try:
   k=get(f"/{layer}/query",{"where":"ProviderName = '"+name.replace("'","''")+"'","returnCountOnly":"true"}).get("count")
   print("COUNT_PROVIDER",name,layer,k,flush=True)
  except Exception as e:print("ERROR",name,layer,e,flush=True)
