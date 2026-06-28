#!/usr/bin/env python3
"""Build a correctly-encoded memegen.link image URL.

memegen.link encodes meme text in the URL *path* (not as query params), so
characters like spaces, '/', '#' and '?' need escaping or the image breaks.
This script applies memegen.link's escaping rules deterministically — no API
key, no network call, just string encoding.

Encoding reference (https://memegen.link):
    space        -> _
    _  (literal) -> __
    -  (literal) -> --
    ?            -> ~q
    &            -> ~a
    %            -> ~p
    #            -> ~h
    /            -> ~s
    \\  (literal) -> ~b
    <            -> ~l
    >            -> ~g
    "            -> '' (two single quotes)
    newline      -> ~n
    empty line   -> _

Usage:
    python3 build_meme_url.py --template mordor \\
        --top "ONE DOES NOT SIMPLY" --bottom "review a 2000 line PR"
    python3 build_meme_url.py --selftest
"""
import argparse
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.memegen.link/images"

# Order matters: escape literal '_' and '-' BEFORE turning spaces into '_',
# otherwise spaces-as-underscores would be indistinguishable from literals.
# The '~x' tokens and "''" introduce no '_', '-' or spaces, so they are safe
# to apply in any order relative to the space substitution that runs last.
_REPLACEMENTS = [
    ("_", "__"),    # literal underscore  -> double underscore
    ("-", "--"),    # literal dash        -> double dash
    ("?", "~q"),
    ("&", "~a"),
    ("%", "~p"),
    ("#", "~h"),
    ("/", "~s"),
    ("\\", "~b"),
    ("<", "~l"),
    (">", "~g"),
    ('"', "''"),
    ("\n", "~n"),
]


def encode(text):
    """Encode a single meme text line for the memegen.link URL path."""
    if not text:
        return "_"  # empty/blank line renders as an empty line
    for char, repl in _REPLACEMENTS:
        text = text.replace(char, repl)
    text = text.replace(" ", "_")
    return text or "_"


def build_url(template, top="", bottom="", ext="png"):
    """Return the full memegen.link image URL with both text lines encoded."""
    return "{}/{}/{}/{}.{}".format(
        BASE, template.strip().lower(), encode(top), encode(bottom), ext
    )


def verify(url, timeout=8, retries=1):
    """GET the URL and confirm it actually renders an image.

    memegen.link runs on Heroku behind Cloudflare; when the render backend is
    down it returns 503 (and Cloudflare may still serve *cached* images with
    200). Posting a URL that 503s leaves a broken image in the PR — so we check
    before proposing. Returns (ok, detail).
    """
    last = "no response"
    # ponytail: one short retry covers a Heroku cold-start; not a full backoff.
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url, method="GET", headers={"User-Agent": "pr-meme/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ctype = r.headers.get("Content-Type", "")
                if r.status == 200 and ctype.startswith("image/"):
                    return True, "200 {}".format(ctype)
                last = "{} {}".format(r.status, ctype or "?")
        except urllib.error.HTTPError as e:
            last = "{} {}".format(e.code, e.reason)
        except Exception as e:  # noqa: BLE001 - network/url errors, report verbatim
            last = "error: {}".format(e)
        if attempt < retries:
            time.sleep(1.5)
    return False, last


def _selftest():
    """Validate the encoding rules the user cares about (spaces, ?, #, /, ...)."""
    cases = [
        ("ONE DOES NOT SIMPLY", "ONE_DOES_NOT_SIMPLY"),
        ("review a 2000 line PR", "review_a_2000_line_PR"),
        ("THIS IS FINE", "THIS_IS_FINE"),
        ("what?", "what~q"),
        ("issue #5", "issue_~h5"),
        ("feat/auth", "feat~sauth"),
        ("snake_case", "snake__case"),
        ("a-b", "a--b"),
        ("50% done", "50~p_done"),
        ("a & b", "a_~a_b"),
        ("", "_"),
        (" ", "_"),
    ]
    ok = True
    for text, expected in cases:
        got = encode(text)
        passed = got == expected
        ok = ok and passed
        print("[{}] {!r:>24} -> {!r}  (expected {!r})".format(
            "ok " if passed else "FAIL", text, got, expected))

    url = build_url("mordor", "ONE DOES NOT SIMPLY", "review a 2000 line PR")
    expected_url = ("https://api.memegen.link/images/mordor/"
                    "ONE_DOES_NOT_SIMPLY/review_a_2000_line_PR.png")
    passed = url == expected_url
    ok = ok and passed
    print("[{}] full url -> {}".format("ok " if passed else "FAIL", url))

    print("\nSELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(
        description="Build a memegen.link image URL with proper escaping.")
    p.add_argument("--template",
                   help="memegen.link template id (e.g. mordor, fine, drake, "
                        "success, fry, interesting)")
    p.add_argument("--top", default="", help="top text line")
    p.add_argument("--bottom", default="", help="bottom text line")
    p.add_argument("--ext", default="png",
                   help="image extension (png, jpg, gif, webp). Default: png")
    p.add_argument("--verify", action="store_true",
                   help="check that the URL actually renders before using it; "
                        "exit code 2 (and RENDER_FAIL line) if it does not")
    p.add_argument("--timeout", type=float, default=8.0,
                   help="seconds to wait per verify request. Default: 8")
    p.add_argument("--selftest", action="store_true",
                   help="run encoding self-tests and exit")
    args = p.parse_args()

    if args.selftest:
        return _selftest()
    if not args.template:
        p.error("--template is required (or use --selftest)")

    url = build_url(args.template, args.top, args.bottom, args.ext)
    print(url)
    if args.verify:
        ok, detail = verify(url, timeout=args.timeout)
        print(("RENDER_OK " if ok else "RENDER_FAIL ") + detail)
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
