#!/usr/bin/env python3
"""
Inline viewer + data into ONE self-contained HTML file, for a hosted demo.

Refuses unless the library's config.json has "demo": true. That flag lives only
in kit/sample/config.json, so a real archive cannot be bundled by accident:
the viewer is meant to travel, your data is not.

  python3 engine/build_index.py  --library kit/sample
  python3 engine/bundle_demo.py  --library kit/sample  --out demo.html
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from libroot import ENGINE, library_root  # noqa: E402

KIT = os.path.dirname(ENGINE)


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as fh:
        return fh.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = library_root()

    cfg_path = os.path.join(root, "config.json")
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    if not cfg.get("demo"):
        sys.exit(f"REFUSED: {root} is not a demo library (config.json lacks \"demo\": true).\n"
                 "Only fictional sample data may be bundled into a shareable page.")

    data = read(root, "data", "library.js")
    if '"demo": true' not in data:
        sys.exit("REFUSED: data/library.js was not built from a demo library. Rebuild it.")

    shell = read(KIT, "index.html")
    css, js = read(KIT, "ui", "app.css"), read(KIT, "ui", "app.js")
    out = (shell
           .replace('<link rel="stylesheet" href="ui/app.css">', "<style>\n" + css + "\n</style>")
           .replace('<script src="data/library.js"></script>', "<script>\n" + data + "\n</script>")
           .replace('<script src="ui/app.js"></script>', "<script>\n" + js + "\n</script>"))
    for needle in ('href="ui/app.css"', 'src="data/library.js"', 'src="ui/app.js"'):
        if needle in out:
            sys.exit(f"bundle failed: {needle} not inlined — index.html changed shape?")
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"Wrote {args.out} ({os.path.getsize(args.out)//1024} KB, demo data only)")


if __name__ == "__main__":
    main()
