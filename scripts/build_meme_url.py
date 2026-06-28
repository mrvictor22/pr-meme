#!/usr/bin/env python3
"""Build a correctly-encoded memegen.link image URL.

memegen.link encodes meme text in the URL *path* (not as query params), so
characters like spaces, '/', '#', '?' AND any non-ASCII byte (acentos, ñ,
emoji) must be escaped or the URL is invalid and the render fails. This script
applies memegen.link's canonical escaping rules and then percent-encodes each
segment — no API key, no required network call, just deterministic encoding.

Two-stage encoding (matches the official memegen `app/utils/text.py::_encode`):

  1. Token replacements (typographic normalization first, then canonical order;
     space comes BEFORE the '~' tokens):
        smart quotes/en-dash -> straight ASCII (so the rules below also
                                canonicalize them: '"' -> "''", '-' -> "--")
        space        -> _
        _  (literal) -> __
        -  (literal) -> --
        ?            -> ~q
        %            -> ~p
        #            -> ~h
        "            -> '' (two single quotes)
        /            -> ~s
        \\  (literal) -> ~b
        newline      -> ~n
        &            -> ~a
        <            -> ~l
        >            -> ~g
        empty line   -> _
     (We do NOT run urllib.unquote first like the upstream API does: our input
     is RAW user text from --top/--bottom, not a pre-encoded URL path, so
     unquoting it would wrongly collapse literal "%XX"-looking sequences.)

  2. Percent-encode the result with urllib.parse.quote, keeping the memegen
     tokens safe (~ _ - . '), so É/ñ/👍/símbolos become %XX instead of raw
     bytes. This is what makes non-ASCII text render (HTTP 200) instead of
     producing an invalid URL.

Known limitation 1: a LITERAL '~' cannot be represented. memegen unquotes the
path before applying token rules, so even "%7E" collapses back to '~' and a
"~q" the user typed is decoded as '?'. There is no reliable escape; we leave
the '~' as-is (it still renders, no crash) and document it. See _selftest.

Known limitation 2: a literal '%' immediately followed by two hex digits
(e.g. "100%ABV") is corrupted by memegen at *render* time, not by us. Our
encode() correctly emits "100~pABV", but when memegen renders it reverses the
'~p' token back to '%' and then unquotes the path, so "%AB" becomes an invalid
byte and shows as '�' (U+FFFD): "100%ABV" renders as "100�V". This is inherent
to memegen (writing "%25ABV" corrupts the same way); avoid that exact form or
put a space/character between the '%' and the two hex digits. The --selftest
pins the local encode() output, not the render. See _selftest.

Known limitation 3: this mirrors memegen's own `_encode` exactly, including its
quirk that a literal '_' followed by a space rewrites "___" -> "__-" globally,
so a run of 3+ spaces on the same line is collapsed too. We keep this on purpose
(diverging would produce a URL memegen never emits, rendering unpredictably).
Reachability is near-zero in real meme text. See encode() and _selftest.

Usage:
    python3 build_meme_url.py --template mordor \\
        --top "ONE DOES NOT SIMPLY" --bottom "review a 2000 line PR"
    python3 build_meme_url.py --selftest
"""
import argparse
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.memegen.link/images"

# Canonical memegen order. Space is substituted BEFORE the '~' tokens, exactly
# like the upstream `_encode`. The smart-punctuation rows run FIRST so their
# ASCII output is also canonicalized by the rules below (a curly '"' becomes a
# straight '"' and then "''"; an en-dash becomes '-' and then "--"); otherwise
# they'd emit non-canonical %22 / single '-' that memegen only fixes via a 301
# redirect. The literal '_' and '-' are then doubled BEFORE the space rule so a
# space-as-underscore is distinguishable from a literal underscore.
_REPLACEMENTS = [
    ("‘", "'"),  # ' left single quote  -> '
    ("’", "'"),  # ' right single quote -> '
    ("“", '"'),  # " left double quote  -> "
    ("”", '"'),  # " right double quote -> "
    ("–", "-"),  # en dash -> hyphen
    ("_", "__"),    # literal underscore -> double underscore
    ("-", "--"),    # literal dash       -> double dash
    (" ", "_"),     # space              -> underscore
    ("?", "~q"),
    ("%", "~p"),
    ("#", "~h"),
    ('"', "''"),    # straight double quote -> two single quotes
    ("/", "~s"),
    ("\\", "~b"),
    ("\n", "~n"),
    ("&", "~a"),
    ("<", "~l"),
    (">", "~g"),
]

# Keep the memegen tokens intact while percent-encoding everything else (so
# acentos/emoji become %XX). '~ _ - .' are URL-unreserved (quote never touches
# them); "'" is NOT, so we add it to preserve the "''" double-quote token.
_SAFE = "~_-.'"


def encode(text):
    """Encode a single meme text line: memegen tokens, then percent-encoding."""
    if not text:
        return "_"  # empty/blank line renders as an empty line
    has_trailing_under = "_ " in text  # literal underscore followed by a space
    for char, repl in _REPLACEMENTS:
        text = text.replace(char, repl)
    if has_trailing_under:
        # Faithfully mirrors memegen's own `_encode` (app/utils/text.py): when a
        # literal '_' is followed by a space it rewrites "___" -> "__-". Note the
        # replace is GLOBAL, so a run of 3+ spaces elsewhere on the same line is
        # also affected — that's memegen's own quirk, NOT ours. Do NOT "fix" this
        # by diverging: we must produce the exact URL memegen produces, or the
        # render becomes unpredictable. See Known limitation 3. (Reachability is
        # near-zero: needs a literal '_'+space AND a 3-space run in one line.)
        text = text.replace("___", "__-")
    text = urllib.parse.quote(text, safe=_SAFE)
    return text or "_"


def build_url(template, top="", bottom="", ext="png", token=None):
    """Return the full memegen.link image URL with both text lines encoded.

    If ``token`` is given, append ``?token=<token>`` so the request uses
    memegen's authenticated route (no watermark, not rate-limited). Without a
    token (the default) the request is anonymous: it may carry a watermark and
    is subject to transient rate-limiting on the unauthenticated route.

    WARNING: the token ends up in the URL. If you post that URL in a public PR
    comment, the token is exposed to anyone who can see the PR. Only use a token
    you don't mind sharing (or in private repos).
    """
    # quote the template too (defense in depth): the built-in ids are plain
    # ASCII, but a custom id with '/', '?' or non-ASCII would otherwise break
    # the path.
    safe_template = urllib.parse.quote(template.strip().lower(), safe="")
    url = "{}/{}/{}/{}.{}".format(
        BASE, safe_template, encode(top), encode(bottom), ext)
    if token:
        url += "?token=" + urllib.parse.quote(token, safe="")
    return url


def verify(url, timeout=12, backoff=(2.0, 5.0, 10.0)):
    """GET the URL and confirm memegen.link actually renders an image.

    Returns ``(ok, kind, detail)`` where ``kind`` is one of:
      "ok"          - HTTP 200 image/* (renders; safe to post).
      "meme_error"  - HTTP 4xx (e.g. 404 = unknown template / invalid URL).
                      This is a BUG in the meme, NOT an outage: fix the meme.
                      Not retried.
      "transient"   - HTTP 5xx / timeout / network error. memegen runs on
                      Heroku; a 5xx is almost always a transient blip
                      (cold-start, router hiccup, or rate-limit of the
                      unauthenticated route), NOT a permanent outage. Retried
                      with backoff before giving up.

    No cache-buster: a plain GET is used on purpose. The previous version forced
    a cache MISS to the origin on every check, which only makes the probable
    cause (rate-limiting of the anonymous route) WORSE. A cached 200 from
    Cloudflare is a *good* sign — it means the exact URL we post renders for
    GitHub's Camo proxy too. So we just do a normal GET and trust the result.
    """
    headers = {"User-Agent": "pr-meme/1.0"}
    last = "no response"
    attempts = len(backoff) + 1
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ctype = r.headers.get("Content-Type", "")
                if r.status == 200 and ctype.startswith("image/"):
                    final = r.geturl()
                    if final != url:
                        # memegen 301'd to its canonical form: the image exists
                        # (still RENDER_OK), but the rewrite signals the text was
                        # non-canonical / possibly corrupt. Warn; keep exit 0.
                        return (True, "ok",
                                "200 {} (memegen reescribió la URL a la forma "
                                "canónica: {} — revisá el texto)".format(
                                    ctype, final))
                    return True, "ok", "200 {}".format(ctype)
                # 200 but not an image: unexpected (e.g. an HTML error page).
                last = "{} {} — respuesta inesperada".format(
                    r.status, ctype or "sin content-type")
        except urllib.error.HTTPError as e:
            if e.code == 414:
                # URI Too Long: the meme text is too long, not a bad template.
                return (False, "meme_error",
                        "{} {} — texto demasiado largo; acortá las líneas "
                        "(no se reintenta)".format(e.code, e.reason))
            if 400 <= e.code < 500:
                # 4xx is deterministic: retrying won't help. Stop now.
                return (False, "meme_error",
                        "{} {} — URL/template inválido; corregí el meme "
                        "(no se reintenta)".format(e.code, e.reason))
            last = "{} {}".format(e.code, e.reason)  # 5xx -> transient
        except Exception as e:  # noqa: BLE001 - network/url errors, report verbatim
            last = "error: {}".format(e)  # timeout/DNS/etc -> transient
        if attempt < attempts - 1:
            time.sleep(backoff[attempt])
    return (False, "transient",
            "{} — transitorio (cold-start / blip del router Heroku / "
            "rate-limit de la ruta sin token); reintentá en unos "
            "segundos".format(last))


def _selftest():
    """Validate the encoding rules offline (no network). Checks spaces, the
    '~' tokens, AND percent-encoding of non-ASCII (acento, ñ, emoji) plus the
    documented literal-'~' limitation."""
    cases = [
        ("ONE DOES NOT SIMPLY", "ONE_DOES_NOT_SIMPLY"),
        ("review a 2000 line PR", "review_a_2000_line_PR"),
        ("THIS IS FINE", "THIS_IS_FINE"),
        ("what?", "what~q"),
        ("issue #5", "issue_~h5"),
        ("feat/auth", "feat~sauth"),
        ("snake_case", "snake__case"),
        ("a-b", "a--b"),
        # literal '_' + space -> "__-" (mirrors memegen's own _encode; see
        # Known limitation 3). The "___"->"__-" is global, so this also collapses
        # a 3-space run on the same line — memegen's quirk, kept on purpose.
        ("a_ b", "a__-b"),
        ("50% done", "50~p_done"),
        # local encode() is correct here, but memegen CORRUPTS this at RENDER:
        # it reverses '~p'->'%' then unquotes, so "%AB" becomes an invalid byte
        # ("100%ABV" renders as "100�V"). We only pin the local encode output.
        ("100%ABV", "100~pABV"),
        ("a & b", "a_~a_b"),
        ("", "_"),
        (" ", "_"),
        # --- non-ASCII: must percent-encode (this is the bug we fixed) ---
        ("ARREGLÉ EL BUG", "ARREGL%C3%89_EL_BUG"),          # acento É
        ("compilación ñ", "compilaci%C3%B3n_%C3%B1"),       # ó + ñ
        ("\U0001f44d", "%F0%9F%91%8D"),                       # emoji 👍
        # --- literal '~': KNOWN LIMITATION, left as-is (renders, decodes to '?')
        ("a~qb", "a~qb"),
    ]
    ok = True
    for text, expected in cases:
        got = encode(text)
        passed = got == expected
        ok = ok and passed
        # ascii() keeps output safe even on a non-UTF8 terminal.
        print("[{}] {:>26} -> {}  (expected {})".format(
            "ok " if passed else "FAIL", ascii(text), ascii(got),
            ascii(expected)))

    url = build_url("mordor", "ONE DOES NOT SIMPLY", "review a 2000 line PR")
    expected_url = ("https://api.memegen.link/images/mordor/"
                    "ONE_DOES_NOT_SIMPLY/review_a_2000_line_PR.png")
    passed = url == expected_url
    ok = ok and passed
    print("[{}] full url -> {}".format("ok " if passed else "FAIL", url))

    # --token appends an authenticated-route query param.
    turl = build_url("success", "hi", "", token="abc123")
    passed = turl.endswith("?token=abc123")
    ok = ok and passed
    print("[{}] token url -> {}".format("ok " if passed else "FAIL", turl))

    print("\nNOTE: a literal '~' (e.g. \"a~qb\") cannot be escaped — memegen "
          "decodes it as a token, so it renders as '?'. Known limitation.")
    print("SELFTEST:", "PASS" if ok else "FAIL")
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
    p.add_argument("--token", default=None,
                   help="optional memegen API token; appended as ?token=... to "
                        "use the authenticated route (no watermark / no "
                        "rate-limit). Not stored anywhere; you pass it. WARNING: "
                        "it ends up in the posted URL — don't use it in a public "
                        "PR unless you're fine exposing the token.")
    p.add_argument("--verify", action="store_true",
                   help="check that the URL actually renders before using it; "
                        "exit code 2 (and RENDER_FAIL line) if it does not")
    p.add_argument("--timeout", type=float, default=12.0,
                   help="seconds to wait per verify request. Default: 12")
    p.add_argument("--selftest", action="store_true",
                   help="run encoding self-tests and exit")
    args = p.parse_args()

    if args.selftest:
        return _selftest()
    if not args.template:
        p.error("--template is required (or use --selftest)")

    url = build_url(args.template, args.top, args.bottom, args.ext, args.token)
    print(url)
    if args.verify:
        ok, kind, detail = verify(url, timeout=args.timeout)
        if ok:
            print("RENDER_OK " + detail)
            return 0
        print("RENDER_FAIL [{}] {}".format(kind, detail))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
