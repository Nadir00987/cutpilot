"""Detached render verification runner (Worker C). Logs to scripts/run.log."""
import json
import os
import subprocess
import sys
import traceback

sys.path.insert(0, "/home/hatch/workspace/cutpilot-ai/backend")

LOG = open("/home/hatch/workspace/cutpilot-ai/scripts/run.log", "a", buffering=1)


def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()


def ffprobe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height,codec_name:format=duration",
         "-of", "json", path], capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def main():
    from app.services.render_pipeline import run_render
    with open("/home/hatch/workspace/cutpilot-ai/storage/projects/test/edit_plan.json") as f:
        plan = json.load(f)

    last = [-1]

    def cb(stage, pct, eta):
        b = int(pct) // 10
        if b != last[0]:
            last[0] = b
            log(f"progress {stage} {pct:.0f}% eta={eta and round(eta,1)}")

    for preset, exp_wh in (("1080p", (1920, 1080)), ("9:16", (1080, 1920))):
        log(f"=== render {preset} start ===")
        try:
            out = run_render("test", preset, plan, cb)
        except Exception:
            log(f"RENDER {preset} FAILED:\n{traceback.format_exc()}")
            continue
        info = ffprobe(out)
        streams = info.get("streams", [])
        vids = [s for s in streams if s.get("codec_name") == "h264"]
        auds = [s for s in streams if s.get("codec_name") == "aac"]
        dur = float(info.get("format", {}).get("duration", 0))
        ok = (vids and auds and (vids[0]["width"], vids[0]["height"]) == exp_wh
              and abs(dur - 24.5) < 1.5)
        log(f"RENDER {preset}: {'PASS' if ok else 'FAIL'} "
            f"{vids[0]['width'] if vids else '?'}x{vids[0]['height'] if vids else '?'} "
            f"audio={'yes' if auds else 'NO'} dur={dur:.2f}s -> {out}")

    log("=== captions 10 styles ===")
    from app.services.captions import STYLES, write_ass
    words = plan["captions"]["words"][:12]
    bad = []
    for name in sorted(STYLES):
        p = write_ass(words, name, 1080, 1920, "bottom",
                      project_id="test", tag=f"style_{name}")
        body = open(p, encoding="utf-8").read()
        if "\\k" not in body or "Dialogue:" not in body or len(body) < 500:
            bad.append(name)
    log(f"CAPTIONS: {'PASS' if not bad else 'FAIL ' + str(bad)}")
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL:\n" + traceback.format_exc())
    log("RUNNER EXIT")
