#!/usr/bin/env python3
"""Reusable provider/denominator extraction from an ArcGIS FCC BDC FeatureServer.

One independent GitHub Actions job per requested provider; keyset pagination and
unique job file names avoid hardcoded run IDs or merged-artifact collisions.
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_SERVICE = "https://services8.arcgis.com/peDZJliSvYims39Q/ArcGIS/rest/services/FCC_Broadband_Data_Collection_December_2024_View/FeatureServer"
DEFAULT_PROVIDERS = "Verizon,T-Mobile,Spectrum,Frontier,Brightspeed,Metronet,Lumos,Optimum,altafiber,Windstream"
PROVIDER_FIELDS = ["OBJECTID", "GEOID", "ProviderName", "FRN", "Technology", "TotalBSLs", "ServedBSLs"]
DENOM_FIELDS = ["OBJECTID", "GEOID", "TotalBSLs", "ServedBSLs"]


def providers_from_text(text):
    names = [x.strip() for x in text.split(",")]
    names = [x for x in names if x]
    if not names or len(names) > 24:
        raise ValueError("Supply 1-24 comma-separated provider names")
    output = []
    seen = set()
    for n in names:
        if len(n) > 90 or not re.fullmatch(r"[a-zA-Z0-9 &.'()+/-]+", n):
            raise ValueError("Invalid provider name: " + n)
        if n.casefold() not in seen:
            seen.add(n.casefold())
            output.append(n)
    return output


def matrix_for(providers):
    result = [{"id": "denominators", "provider": "", "kind": "denominators"}]
    result.extend({"id": f"p{i:02d}", "provider": name, "kind": "provider"}
                  for i, name in enumerate(providers, 1))
    return {"include": result}


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path.rstrip("/").endswith("/FeatureServer") or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("Dataset must be an HTTPS ArcGIS FeatureServer URL (no query string)")
    return url.rstrip("/")


def request_json(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "StanceFCCRefresh/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                value = json.load(resp)
            if isinstance(value, dict) and value.get("error"):
                raise RuntimeError(str(value["error"]))
            return value
        except Exception as exc:
            if attempt == 5:
                raise
            print(f"retry {attempt+1}: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(min(40, 2 ** attempt * 2))


def discover_layers(base):
    service = request_json(base, {"f": "json"})
    layers = service.get("layers", []) + service.get("tables", [])
    def layer_for(needle, required):
        for item in layers:
            name = item.get("name", "").lower()
            if needle not in name:
                continue
            lid = item["id"]
            info = request_json(base + "/" + str(lid), {"f": "json"})
            cols = {v["name"] for v in info.get("fields", [])}
            if set(required).issubset(cols):
                return lid
        raise ValueError("Dataset lacks compatible H3 " + needle + " table/layer")
    provider_id = layer_for("bdc records for h3", PROVIDER_FIELDS)
    denominator_id = layer_for("h3 resolution", DENOM_FIELDS)
    return service, provider_id, denominator_id


def where_for(provider):
    if not provider:
        return "1=1"
    escaped = provider.replace("'", "''")
    return f"ProviderName LIKE '%{escaped}%'"


def extract(base, kind, provider, output_id, output_dir):
    service, provider_id, denom_id = discover_layers(base)
    if kind not in ("denominators", "provider"):
        raise ValueError("Invalid extraction kind")
    if not re.fullmatch(r"(denominators|p[0-9]{2})", output_id):
        raise ValueError("Invalid output ID")
    if kind == "provider" and not provider:
        raise ValueError("Missing provider")
    layer = denom_id if kind == "denominators" else provider_id
    fields = DENOM_FIELDS if kind == "denominators" else PROVIDER_FIELDS
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / (output_id + "_fcc_h3.csv")
    partial = output_dir / (output_id + "_fcc_h3.csv.part")
    cursor = 0
    rows_written = 0
    pages = 0
    with partial.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        while True:
            where = f"OBJECTID > {cursor}"
            if provider and kind == "provider":
                where += " AND (" + where_for(provider) + ")"
            payload = request_json(base + f"/{layer}/query", {
                "f": "json", "where": where, "outFields": ",".join(fields),
                "returnGeometry": "false", "orderByFields": "OBJECTID ASC",
                "resultRecordCount": 2000
            })
            records = payload.get("features")
            if not isinstance(records, list):
                raise RuntimeError("Dataset returned an invalid features payload")
            if not records:
                break
            for row in records:
                data = row["attributes"]
                oid = int(data["OBJECTID"])
                if oid <= cursor:
                    raise RuntimeError("Non-increasing OBJECTID; refusing incomplete export")
                cursor = oid
                writer.writerow({key: data.get(key) for key in fields})
                rows_written += 1
            pages += 1
            if pages % 100 == 0:
                print("progress", kind, provider, "pages", pages, "rows", rows_written, flush=True)
            if pages >= 30000:
                raise RuntimeError("Pagination safety limit exceeded; not publishing incomplete data")
            # Do not stop on a short page: servers may cap requested 2000 rows.
    partial.replace(dest)
    manifest = {
        "source": base, "service_name": service.get("name", ""),
        "service_item_id": service.get("serviceItemId", ""),
        "provider_filter": provider, "kind": kind, "output_id": output_id,
        "layer": layer, "rows": rows_written, "pages": pages,
        "extracted_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "note": "Coverage vintage must be confirmed from the selected source metadata."
    }
    (output_dir / (output_id + "_manifest.json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("DONE", json.dumps(manifest), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--providers", default=DEFAULT_PROVIDERS)
    run = sub.add_parser("run")
    run.add_argument("--service-url", default=DEFAULT_SERVICE)
    run.add_argument("--kind", required=True)
    run.add_argument("--provider", default="")
    run.add_argument("--output-id", required=True)
    run.add_argument("--output-dir", default="out")
    a = ap.parse_args(argv)
    if a.action == "plan":
        result = json.dumps(matrix_for(providers_from_text(a.providers)), separators=(",", ":"))
        print(result)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("matrix=" + result + "\n")
    else:
        extract(validate_url(a.service_url), a.kind, a.provider, a.output_id, Path(a.output_dir))


if __name__ == "__main__":
    main()
