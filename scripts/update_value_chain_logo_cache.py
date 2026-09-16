"""Fetch verified raster logos once; the website only reads local static assets."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.config import load_dotenv

load_dotenv(ROOT / ".env.development.local")
DATA = ROOT / "data/value-chain"
ASSETS = ROOT / "public/company-logos"
MAX_BYTES = 4 * 1024 * 1024
DOMAIN_OVERRIDES = {
    "asml": "asml.com", "tel": "tel.com", "lam": "lamresearch.com",
    "amat": "appliedmaterials.com", "axcelis": "axcelis.com", "tsmc": "tsmc.com",
    "kla": "kla.com", "airliquide": "airliquide.com", "jsr": "jsr.co.jp",
    "shinetsu": "shinetsu.co.jp", "sumco": "sumcosi.com", "disco": "disco.co.jp",
    "ibiden": "ibiden.com", "dupont": "dupont.com", "onsemi": "onsemi.com",
    "skmaterials": "skspecialty.com", "foosung": "foosungchem.com",
    "gs": "gs.co.kr", "heungguOil": "hunggu.kr",
}


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.2)


def normalize_domain(value):
    host = urlparse(value if "://" in value else "https://" + value).hostname or ""
    host = host.lower().removeprefix("www.").rstrip(".")
    if "." not in host or any(c.isspace() for c in host):
        return ""
    return host.encode("idna").decode("ascii")


def discover_domain(company):
    if company.get("domain"):
        return normalize_domain(company["domain"])
    if company["id"] in DOMAIN_OVERRIDES:
        return DOMAIN_OVERRIDES[company["id"]]
    if not os.getenv("DART_API_KEY"):
        return ""
    from scripts.sources.dart_api import get_corp_code
    corp = get_corp_code(company["name"], stock_code=company.get("ticker", ""))
    if not corp or (company.get("ticker") and corp["stock_code"].strip() != company["ticker"]):
        return ""
    response = requests.get("https://opendart.fss.or.kr/api/company.json", params={
        "crtfc_key": os.environ["DART_API_KEY"], "corp_code": corp["corp_code"],
    }, timeout=(10, 20))
    response.raise_for_status()
    data = response.json()
    return normalize_domain(data.get("hm_url", "")) if data.get("status") == "000" else ""


def decode_image(content_type, content):
    if not content_type.lower().startswith("image/") or not 64 <= len(content) <= MAX_BYTES:
        raise ValueError("invalid image response")
    with Image.open(BytesIO(content)) as original:
        if original.width < 16 or original.height < 16 or original.width * original.height > 16_000_000:
            raise ValueError("invalid image dimensions")
        original.verify()
    with Image.open(BytesIO(content)) as original:
        result = original.convert("RGBA")
        if result.getchannel("A").getbbox() is None:
            raise ValueError("empty image")
        result.thumbnail((768, 768), Image.Resampling.LANCZOS)
        return result


def logo_background(path):
    with Image.open(path) as image:
        image = image.convert("RGBA")
        image.thumbnail((64, 64))
        pixels = [image.getpixel((x, y)) for y in range(image.height) for x in range(image.width)]
        visible = [(r + g + b) / 3 for r, g, b, a in pixels if a > 128]
        transparent = sum(a < 64 for _, _, _, a in pixels) / len(pixels)
        return "dark" if visible and transparent > .1 and sum(visible) / len(visible) > 185 else "light"


def logo_canvas_color(path):
    with Image.open(path) as image:
        image = image.convert("RGBA")
        corners = [image.getpixel((x, y)) for x, y in ((0, 0), (image.width - 1, 0), (0, image.height - 1), (image.width - 1, image.height - 1))]
        if all(pixel[3] > 240 for pixel in corners) and all(max(pixel[i] for pixel in corners) - min(pixel[i] for pixel in corners) < 20 for i in range(3)):
            return "#" + "".join(f"{round(sum(pixel[i] for pixel in corners) / 4):02x}" for i in range(3))
    return "#23313d" if logo_background(path) == "dark" else "#ffffff"


def logo_candidate_score(logo, fmt):
    # Prefer a usable wordmark over a tiny icon; never upscale the source.
    width, height = fmt.get("width") or 0, fmt.get("height") or 0
    resolution = min(width, 768) * min(height, 384)
    return (resolution >= 16_384, resolution, logo.get("theme") == "light", logo.get("type") == "logo")


def download_logo(payload, destination):
    candidates = []
    for logo in payload.get("logos", []):
        for fmt in logo.get("formats", []):
            if fmt.get("format") not in ("png", "webp", "jpeg", "jpg"):
                continue
            score = logo_candidate_score(logo, fmt)
            candidates.append((score, fmt["src"]))
    for _, url in sorted(candidates, key=lambda item: item[0], reverse=True):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".brandfetch.io"):
            continue
        try:
            with requests.get(url, timeout=(10, 20), stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                content = bytearray()
                for block in response.iter_content(65536):
                    content.extend(block)
                    if len(content) > MAX_BYTES:
                        raise ValueError("image too large")
                image = decode_image(response.headers.get("Content-Type", ""), content)
                temporary = destination.with_suffix(".tmp")
                image.save(temporary, format="PNG")
                temporary.replace(destination)
                return url
        except (requests.RequestException, ValueError, OSError):
            continue
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--domains-only", action="store_true")
    parser.add_argument("--only", help="Comma-separated company IDs")
    parser.add_argument("--audit-local", action="store_true", help="Recalculate logo plate contrast without API calls")
    args = parser.parse_args()
    key = os.getenv("BRANDFETCH_API_KEY", "")
    if not key and not args.domains_only and not args.audit_local:
        print("[logos] BRANDFETCH_API_KEY missing; keeping existing cache.")
        return
    companies = read_json(DATA / "companies.json", [])
    cache = read_json(DATA / "logos.json", {"provider": "Brandfetch", "companies": {}})
    cache.setdefault("unavailable", {})
    ASSETS.mkdir(parents=True, exist_ok=True)
    if args.audit_local:
        for company_id, entry in cache["companies"].items():
            path = ASSETS / f"{company_id}.png"
            if path.exists():
                entry["background"] = logo_background(path)
                entry["canvasColor"] = logo_canvas_color(path)
                with Image.open(path) as image:
                    entry["width"], entry["height"] = image.size
        save_json(DATA / "logos.json", cache)
        return
    attempts = 0
    for company in companies:
        company_id = company["id"]
        if args.only and company_id not in args.only.split(","):
            continue
        try:
            domain = discover_domain(company)
        except (requests.RequestException, ValueError):
            print(f"[logos] {company_id}: domain lookup unavailable", flush=True)
            continue
        if not domain:
            print(f"[logos] {company_id}: no verified domain", flush=True)
            continue
        if company.get("domain") != domain:
            company["domain"] = domain
            save_json(DATA / "companies.json", companies)
        if args.domains_only:
            continue
        existing = cache["companies"].get(company_id, {})
        destination = ASSETS / f"{company_id}.png"
        if not args.refresh:
            fetched = existing.get("fetchedAt")
            if fetched and existing.get("domain") == domain and destination.exists():
                if (datetime.now(timezone.utc) - datetime.fromisoformat(fetched)).days < 30:
                    continue
            failed = cache["unavailable"].get(company_id)
            if failed and failed.get("domain") == domain:
                if (datetime.now(timezone.utc) - datetime.fromisoformat(failed["checkedAt"])).days < 7:
                    continue
        if attempts >= args.limit:
            continue
        attempts += 1
        try:
            response = requests.get(f"https://api.brandfetch.io/v2/brands/{domain}",
                                    headers={"Authorization": f"Bearer {key}"}, timeout=(8, 12))
            if response.status_code in (401, 402, 403, 429):
                print(f"[logos] API stopped ({response.status_code}); previous cache retained.", flush=True)
                break
            if response.status_code == 404:
                cache["unavailable"][company_id] = {"domain": domain, "reason": "not_found", "checkedAt": datetime.now(timezone.utc).isoformat()}
                save_json(DATA / "logos.json", cache)
                print(f"[logos] {company_id}: not indexed", flush=True)
                continue
            response.raise_for_status()
            payload = response.json()
            if normalize_domain(payload.get("domain", "")) != domain:
                print(f"[logos] {company_id}: domain mismatch, skipped", flush=True)
                continue
            source = download_logo(payload, destination)
            if source:
                with Image.open(destination) as image:
                    width, height = image.size
                cache["companies"][company_id] = {
                    "domain": domain, "src": f"/company-logos/{company_id}.png",
                    "source": source, "brandName": payload.get("name", ""),
                    "background": logo_background(destination),
                    "canvasColor": logo_canvas_color(destination),
                    "width": width, "height": height,
                    "fetchedAt": datetime.now(timezone.utc).isoformat(),
                }
                cache["unavailable"].pop(company_id, None)
                save_json(DATA / "logos.json", cache)
                print(f"[logos] {company_id}: saved", flush=True)
            else:
                cache["unavailable"][company_id] = {"domain": domain, "reason": "no_valid_raster", "checkedAt": datetime.now(timezone.utc).isoformat()}
                save_json(DATA / "logos.json", cache)
                print(f"[logos] {company_id}: no valid raster logo", flush=True)
        except (requests.RequestException, ValueError, OSError):
            # Never log request objects: DART URLs contain credentials.
            print(f"[logos] {company_id}: unavailable; previous cache retained", flush=True)
    print(f"[logos] Coverage: {len(cache['companies'])}/{len(companies)}; domains: {sum(bool(c.get('domain')) for c in companies)}")


if __name__ == "__main__":
    main()
