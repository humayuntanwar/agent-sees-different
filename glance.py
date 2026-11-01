"""glance: compare what an agent reads (accessibility tree) with what a human sees (pixels).

Flags two kinds of mismatch inside the page area:
  tree_only   - text in the tree that OCR can't find on screen (hidden instructions, swapped amounts, renamed buttons)
  screen_only - text on screen the tree doesn't contain (canvas text, images of text, aria-hidden values)
"""
import re
from difflib import SequenceMatcher

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

TEXT_ROLES = {"statictext", "heading", "button", "link", "image", "note", "label", "textfield", "cell"}
_ocr = None


def norm(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def tree_texts(snapshot):
    """Names of text-bearing nodes under the web page root, plus the page bounds."""
    texts, page = [], {}

    def walk(node, in_page):
        role = node.get("role")
        if role == "webarea":
            in_page, page["bounds"] = True, node.get("bounds")
        if in_page and role in TEXT_ROLES:
            for key in ("name", "value"):
                if node.get(key):
                    texts.append({"role": role, "text": node[key]})
        for child in node.get("children", []):
            walk(child, in_page)

    walk(snapshot["data"]["tree"], False)
    return texts, page.get("bounds")


def screen_lines(png_path, bounds=None):
    global _ocr
    _ocr = _ocr or RapidOCR()
    img = Image.open(png_path).convert("RGB")
    if bounds:
        x, y, w, h = (int(bounds[k]) for k in ("x", "y", "width", "height"))
        img = img.crop((x, y, x + w, y + h))
    result, _ = _ocr(np.array(img))
    return [line[1] for line in (result or [])]


def seen(needle, haystack, threshold=0.9):
    """True if needle appears (fuzzily) inside haystack."""
    needle, haystack = norm(needle), norm(haystack)
    if not needle:
        return True
    if needle in haystack:
        return True
    window = len(needle)
    best = max((SequenceMatcher(None, needle, haystack[i:i + window]).ratio()
                for i in range(max(1, len(haystack) - window + 1))), default=0)
    return best >= threshold


def glance(snapshot, png_path):
    texts, bounds = tree_texts(snapshot)
    lines = screen_lines(png_path, bounds)
    screen = " | ".join(lines)
    tree = " | ".join(t["text"] for t in texts)
    # OCR is unreliable on 1-2 character strings, so those are skipped
    tree_only = [t for t in texts if len(norm(t["text"])) > 2 and not seen(t["text"], screen)]
    screen_only = [line for line in lines if not seen(line, tree)]
    return {"tree_only": tree_only, "screen_only": screen_only, "ocr_lines": lines}


if __name__ == "__main__":
    import json, sys
    report = glance(json.load(open(sys.argv[1])), sys.argv[2])
    print(json.dumps({k: v for k, v in report.items() if k != "ocr_lines"}, indent=2))
