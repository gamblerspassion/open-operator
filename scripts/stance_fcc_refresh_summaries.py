#!/usr/bin/env python3
"""Aggregate H3-derived ZCTA coverage into ZIP, city/place, county and state CSVs."""
import argparse,csv,io,json,urllib.request
from collections import defaultdict
from pathlib import Path

BASE="https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
FIELDS=["area_id","area_name","state_fips","provider_as_filed","technology_code","estimated_covered_locations","estimated_market_locations","estimated_coverage_pct","source_zctas"]

def fraction(row):
    whole=float(row.get("AREALAND_ZCTA5_20") or 0)
    part=float(row.get("AREALAND_PART") or 0)
    return max(0,min(1,part/whole)) if whole else 0

def crosswalk(kind,folder):
    name=f"tab20_zcta520_{kind}20_natl.txt"
    local=folder/name
    if not local.exists():
        with urllib.request.urlopen(BASE+name,timeout=180) as r:
            local.write_bytes(r.read())
    key="COUNTY" if kind=="county" else "PLACE"
    relations=defaultdict(list)
    with local.open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f,delimiter="|"):
            zipid=row.get("GEOID_ZCTA5_20","").zfill(5)
            areaid=row.get("GEOID_"+key+"_20","")
            if not zipid or not areaid:continue
            factor=fraction(row)
            if factor>0:
                relations[zipid].append((areaid,row.get("NAMELSAD_"+key+"_20",""),factor))
    return relations

def rows_from_zip(path):
    with path.open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            den=float(r["zip_total_bsls"] or 0)
            covered=float(r["provider_served_bsls"] or 0)
            if den<=0:continue
            yield (r["zcta"].zfill(5),r["provider_as_filed"],str(r["technology_code"]),min(covered,den),den)

def write_rows(path,areas):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(FIELDS)
        for (id_,name,state,p,t),(covered,den,zips) in sorted(areas.items()):
            w.writerow([id_,name,state,p,t,round(covered,2),round(den,2),
                        round(min(100,100*covered/den),3) if den else "",len(zips)])

def group_zip(values):
    out={}
    for z,p,t,covered,den in values:
        out[(z,z,"",p,t)]=(covered,den,{z})
    return out

def group_relation(values,lookup,state_mode=False):
    sums=defaultdict(lambda:[0.0,0.0,set()])
    for z,p,t,covered,den in values:
        for areaid,name,factor in lookup.get(z,[]):
            if state_mode:
                areaid=areaid[:2];name=areaid
            key=(areaid,name,areaid[:2],p,t)
            s=sums[key];s[0]+=covered*factor;s[1]+=den*factor;s[2].add(z)
    return sums

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--zip-csv",default="zip_results/national_provider_technology_zcta_estimates.csv")
    a.add_argument("--output-dir",default="coverage_results")
    args=a.parse_args()
    target=Path(args.output_dir);target.mkdir(parents=True,exist_ok=True)
    values=list(rows_from_zip(Path(args.zip_csv)))
    if not values:raise RuntimeError("No ZIP coverage rows to aggregate")
    write_rows(target/"coverage_zip.csv",group_zip(values))
    county=crosswalk("county",target)
    place=crosswalk("place",target)
    write_rows(target/"coverage_county.csv",group_relation(values,county))
    write_rows(target/"coverage_city.csv",group_relation(values,place))
    # State from ZCTA-to-county geographic overlaps. Avoid duplicating overlap
    # denominators by merging all counties belonging to the same state.
    state_lookup=defaultdict(list)
    for z,rec in county.items():
        amounts=defaultdict(float)
        for id_,name,factor in rec:
            amounts[id_[:2]]+=factor
        state_lookup[z]=[(state,state,min(1,frac)) for state,frac in amounts.items()]
    write_rows(target/"coverage_state.csv",group_relation(values,state_lookup,True))
    manifest={
      "source_zip_csv":str(args.zip_csv),"input_provider_technology_zctas":len(values),
      "geography":"Census 2020 ZCTA/county/place relationship files; area-weighted approximation",
      "outputs":["coverage_zip.csv","coverage_city.csv","coverage_county.csv","coverage_state.csv"],
      "limitations":["City estimates refer to 2020 incorporated places or census-designated places, not USPS mailing city boundaries.",
                     "County, state and city serviceable locations are allocated by land-area overlap, not address positions.",
                     "Do not sum technology-specific rows to estimate a provider union footprint.",
                     "Coverage is not order qualification, an approved campaign, or a commission guarantee."]}
    (target/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))

if __name__=="__main__":main()
