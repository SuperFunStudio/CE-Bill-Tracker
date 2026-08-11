"""Dump GA4 (property 529411970) CONFIG -- streams, enhanced measurement, custom dimensions, key events.

The companion to ga4_report.py: that one reads the numbers, this one reads the settings that decide
whether the numbers mean anything. Two GA config mistakes are invisible in the reports themselves and
cost us real data before:

  1. Enhanced Measurement's "page changes based on browser history events" double-fires page_view on
     every SPA route change, on top of the one RouteAnalytics.tsx sends. Inflates page_view ~2x. The
     visible "Page views" toggle in the GA UI CANNOT be turned off -- only that advanced sub-checkbox.
  2. Custom dimensions are NOT retroactive. An event param that isn't registered here reads "(not set)"
     in every report, forever, for every event that fired before registration.

So when a report looks wrong, check config here before doubting the instrumentation.

Reading the output: the Admin API omits false booleans (proto3), so a MISSING flag means disabled.
`pageChangesEnabled` absent = the double-count fix is in place. `streamEnabled` absent = Enhanced
Measurement is off entirely, which also kills outbound clicks / scrolls / site search.

Auth: same service account key as ga4_report.py (~/.gcp/ga4-reader.json, override with GA4_KEY_FILE).
Needs a GA4 Viewer grant under Admin -> Property access management; GCP IAM grants nothing here.

Usage:
  venv/Scripts/python scripts/ga4_admin_check.py
"""
import os
import sys
from pathlib import Path

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

PROPERTY_ID = "529411970"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
BASE = "https://analyticsadmin.googleapis.com"
DEFAULT_KEY = Path.home() / ".gcp" / "ga4-reader.json"


def get(headers, url):
    r = requests.get(url, headers=headers, timeout=30)
    ctype = r.headers.get("content-type", "")
    return r.status_code, (r.json() if ctype.startswith("application/json") else r.text)


def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main():
    key_path = Path(os.environ.get("GA4_KEY_FILE", DEFAULT_KEY))
    if not key_path.exists():
        sys.exit(f"No service account key at {key_path} -- see the docstring in scripts/ga4_report.py")
    creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=[SCOPE])
    creds.refresh(AuthRequest())
    headers = {"Authorization": f"Bearer {creds.token}"}

    section("DATA STREAMS + ENHANCED MEASUREMENT")
    code, streams = get(headers, f"{BASE}/v1beta/properties/{PROPERTY_ID}/dataStreams")
    if code != 200:
        print(f"HTTP {code}: {str(streams)[:400]}")
    else:
        for s in streams.get("dataStreams", []):
            name = s["name"]
            print(f"\nstream: {s.get('displayName')}  ({name})  type={s.get('type')}")
            if s.get("type") != "WEB_DATA_STREAM":
                continue
            wd = s.get("webStreamData", {})
            print(f"  measurementId: {wd.get('measurementId')}  uri: {wd.get('defaultUri')}")
            c, em = get(headers, f"{BASE}/v1alpha/{name}/enhancedMeasurementSettings")
            if c != 200:
                print(f"  enhancedMeasurement: HTTP {c} -> {str(em)[:300]}")
                continue
            print("  --- enhanced measurement (absent flag == disabled) ---")
            for k, v in sorted(em.items()):
                if k != "name":
                    print(f"    {k}: {v}")
            if "pageChangesEnabled" in em:
                print("    !! pageChangesEnabled is ON -- page_view is being double-counted on SPA nav")

    section("CUSTOM DIMENSIONS")
    code, cd = get(headers, f"{BASE}/v1beta/properties/{PROPERTY_ID}/customDimensions")
    if code != 200:
        print(f"HTTP {code}: {str(cd)[:400]}")
    else:
        dims = cd.get("customDimensions", [])
        print(f"({len(dims)} registered)" if dims else "(none registered)")
        for d in dims:
            print(f"  {d.get('parameterName'):24} scope={d.get('scope'):10} name={d.get('displayName')}")

    section("KEY EVENTS (conversions)")
    code, ke = get(headers, f"{BASE}/v1beta/properties/{PROPERTY_ID}/keyEvents")
    if code != 200:
        print(f"HTTP {code}: {str(ke)[:300]}")
    else:
        evs = ke.get("keyEvents", [])
        if not evs:
            print("(none marked)")
        for e in evs:
            print(f"  {e.get('eventName')}  countingMethod={e.get('countingMethod')}")


if __name__ == "__main__":
    main()
