"""B-roll resolution engine (Worker C).

``resolve_broll(plan, assets_dir)`` turns each plan broll[] item into a
concrete overlay spec for render_pipeline. Times in the plan are SOURCE
time; the caller passes a ``time_map`` callable (source->edited seconds)
and this module maps/clips every item, dropping items whose span was cut.

Resolution order per item:
  1. plan item has "file"/"source" pointing at an existing file under
     assets_dir (storage/assets/broll) -> use it (trim to span, scale/pad,
     light colour normalisation).
  2. PEXELS_API_KEY / PIXABAY_API_KEY set -> search keyword, download,
     cache under assets_dir/pexels|pixabay, then use it.
  3. else -> mode forced to "keep" (talking head stays), item keeps its
     "prompt_suggestion" for the AI-B-roll backlog. NEVER insert
     irrelevant footage.

Returned spec (overlay geometry, times in EDITED seconds):
  {"mode": "overlay"|"takeover"|"split", "file": path|None,
   "t0": float, "t1": float, "x": expr, "y": expr, "w": int, "h": int,
   "note": str, "prompt_suggestion": str|None}

B-roll audio is always muted (video stream only; main dialogue stays
dominant at 100%, b-roll contributes 0%).
"""

import hashlib
import os

import httpx

SUPPORTED_EXTS = (".mp4", ".mov", ".webm", ".mkv")


def _safe_name(keyword: str) -> str:
    h = hashlib.sha1(keyword.encode()).hexdigest()[:10]
    clean = "".join(c if c.isalnum() else "_" for c in keyword.lower())[:40]
    return f"{clean}_{h}.mp4"


# ------------------------------------------------------------- stock fetch ---
def _pexels_search(keyword: str, api_key: str, cache_dir: str) -> str | None:
    """Search Pexels video API, download first landscape result, cache it."""
    url = "https://api.pexels.com/videos/search"
    try:
        r = httpx.get(url, params={"query": keyword, "per_page": 3,
                                   "orientation": "landscape", "size": "medium"},
                      headers={"Authorization": api_key}, timeout=30)
        r.raise_for_status()
        videos = r.json().get("videos", [])
        for v in videos:
            files = sorted(v.get("video_files", []),
                           key=lambda f: f.get("width", 0))
            files = [f for f in files if f.get("link", "").endswith(".mp4")]
            if not files:
                continue
            link = files[0]["link"]
            dest = os.path.join(cache_dir, "pexels", _safe_name(keyword))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with httpx.stream("GET", link, timeout=120) as s:
                s.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in s.iter_bytes(1 << 20):
                        fh.write(chunk)
            return dest
    except Exception:
        return None
    return None


def _pixabay_search(keyword: str, api_key: str, cache_dir: str) -> str | None:
    url = "https://pixabay.com/api/videos/"
    try:
        r = httpx.get(url, params={"key": api_key, "q": keyword, "per_page": 3},
                      timeout=30)
        r.raise_for_status()
        for hit in r.json().get("hits", []):
            vids = hit.get("videos", {})
            best = vids.get("medium") or vids.get("small") or vids.get("large")
            if not best:
                continue
            dest = os.path.join(cache_dir, "pixabay", _safe_name(keyword))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with httpx.stream("GET", best["url"], timeout=120) as s:
                s.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in s.iter_bytes(1 << 20):
                        fh.write(chunk)
            return dest
    except Exception:
        return None
    return None


def _find_local(keyword: str, filename: str | None, assets_dir: str) -> str | None:
    if filename:
        cand = (filename if os.path.isabs(filename)
                else os.path.join(assets_dir, filename))
        if os.path.exists(cand):
            return cand
    # keyword match against cached/local files
    key = keyword.lower().replace(" ", "_")
    for root, _ds, fs in os.walk(assets_dir):
        for f in fs:
            if f.lower().endswith(SUPPORTED_EXTS) and key in f.lower():
                return os.path.join(root, f)
    return None


# ------------------------------------------------------------------ resolve ---
def resolve_broll(plan: dict, assets_dir: str,
                  time_map=None) -> list[dict]:
    """Resolve plan["broll"] into overlay specs (edited-time).

    time_map: callable source_sec -> edited_sec (from render_pipeline).
    Items fully inside cut regions (t1 <= t0 after mapping) are dropped.
    """
    items = plan.get("broll") or []
    if time_map is None:
        time_map = lambda t: t  # noqa: E731
    specs = []
    for it in items:
        s, e = float(it.get("start", 0)), float(it.get("end", 0))
        t0, t1 = time_map(s), time_map(e)
        if t1 - t0 < 0.3:
            continue  # span was cut away
        keyword = it.get("keyword") or it.get("text") or "b-roll"
        mode = (it.get("mode") or "overlay").lower()
        if mode not in ("overlay", "takeover", "split", "keep"):
            mode = "overlay"

        path = _find_local(keyword, it.get("file") or it.get("source"),
                           assets_dir)
        note = ""
        if not path:
            pex = os.environ.get("PEXELS_API_KEY")
            pix = os.environ.get("PIXABAY_API_KEY")
            if pex:
                path = _pexels_search(keyword, pex, assets_dir)
                note = "pexels" if path else "pexels failed"
            elif pix:
                path = _pixabay_search(keyword, pix, assets_dir)
                note = "pixabay" if path else "pixabay failed"
        if not path:
            specs.append({
                "mode": "keep", "file": None, "t0": t0, "t1": t1,
                "x": "0", "y": "0", "w": 0, "h": 0,
                "note": note or "no footage found",
                "prompt_suggestion": it.get("prompt_suggestion")
                or f"Cinematic b-roll: {keyword}, shallow depth of field",
            })
            continue
        specs.append({
            "mode": mode, "file": path, "t0": t0, "t1": t1,
            "x": "0", "y": "0", "w": 0, "h": 0,  # geometry set by renderer
            "note": note or "local",
            "prompt_suggestion": None,
        })
    return specs
