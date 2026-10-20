import csv,urllib.request,io,json,pathlib,collections
out=pathlib.Path("geo_out");out.mkdir(exist_ok=True)
url="https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt"
with urllib.request.urlopen(url,timeout=90) as res: content=res.read().decode("utf-8-sig")
reader=csv.DictReader(io.StringIO(content),delimiter="|")
print("FIELDS",reader.fieldnames,flush=True)
rows=list(reader)
print("ROWCOUNT",len(rows),"SAMPLE",rows[:2],flush=True)
(out/"census_zip_county_crosswalk_raw.txt").write_text(content)
(out/"metadata.json").write_text(json.dumps({"source":url,"count":len(rows),"columns":reader.fieldnames,"description":"2020 ZIP-area geographic crosswalk only, NOT broadband vintage."},indent=2))
