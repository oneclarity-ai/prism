"""Deterministic CSV validator. Usage: csvcheck.py FILE [expected_rows]. Prints structure facts only (no cell contents beyond header names)."""
import csv, sys, re, io
path = sys.argv[1]; expected = int(sys.argv[2]) if len(sys.argv) > 2 else None
raw = open(path, "rb").read()
print("bytes:", len(raw), "bom:", raw.startswith(b"\xef\xbb\xbf"), "crlf:", b"\r\n" in raw)
try:
    text = raw.decode("utf-8-sig")
except UnicodeDecodeError as e:
    print("NOT UTF-8:", e); sys.exit(1)
rows = list(csv.reader(io.StringIO(text, newline="")))
hdr, body = rows[0], rows[1:]
print("headers(%d):" % len(hdr), hdr)
print("rows:", len(body), "expected:", expected, "MATCH" if expected is None or len(body)==expected else "MISMATCH")
bad = [i+2 for i, r in enumerate(body) if len(r) != len(hdr)]
print("ragged rows (line idx):", bad)
for j, h in enumerate(hdr):
    vals = [r[j] for r in body if len(r) == len(hdr)]
    empty = sum(1 for v in vals if not v.strip())
    print(f"  col {h!r}: empty={empty}/{len(vals)}")
key = hdr[0]
firsts = [r[0].strip().lower() for r in body if r]
print("duplicate first-column values:", sorted({v for v in firsts if firsts.count(v) > 1}))
urls = [u for r in body for u in re.findall(r"https?://\S+", ",".join(r))]
print("url count:", len(urls))
want = ["company","website","industry","location","size","signal","use case","decision","title","profile","email","outreach","source","validation","confidence"]
print("required-column coverage:", {w: any(w in h.lower() for h in hdr) for w in want})
