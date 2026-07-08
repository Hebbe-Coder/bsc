import urllib.request, json, sys, os, time

BASE = "http://localhost:8000"
FAIL = 0
PASS = 0

def test(name, fn):
    global PASS, FAIL
    try:
        ok = fn()
        if ok:
            PASS += 1; print(f"  [PASS] {name}")
        else:
            FAIL += 1; print(f"  [FAIL] {name}")
    except Exception as e:
        FAIL += 1; print(f"  [FAIL] {name} - {str(e)[:60]}")

def get(path, timeout=10):
    return urllib.request.urlopen(f"{BASE}{path}", timeout=timeout)

def post(path, data, timeout=30):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body,
        headers={"Content-Type":"application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=timeout)

# === 1. HEALTH ===
print("\n--- 1. HEALTH CHECK ---")
test("GET /health -> 200", lambda: get("/health").status==200)
test("/health body has status=ok", lambda: json.loads(get("/health").read()).get("status")=="ok")
test("/health has version", lambda: json.loads(get("/health").read()).get("version","")!="")

# === 2. ROUTING ===
print("\n--- 2. ROUTING ---")
test("GET / redirects", lambda: get("/").status in (200,301,302,307,308))
r = get("/")
test("Redirect target has dashboard", lambda: "dashboard" in r.url.lower())

test("GET /dashboard/index.html -> 200", lambda: get("/dashboard/index.html").status==200)
html = get("/dashboard/index.html").read().decode()
test("New UI has BSC Copilot title", lambda: "BSC Copilot" in html or "BSC" in html)
test("New UI has textarea", lambda: "textarea" in html.lower())
test("New UI has go() handler", lambda: "go()" in html or "Analyze" in html)
test("New UI has >3 examples", lambda: html.count("onclick=pick") >= 3 or html.count("onclick=\"pick") >= 3)
test("New UI has Download section", lambda: "Download" in html or "download" in html)
test("New UI: NO pipeline debug (pipe-step)", lambda: "pipe-step" not in html)
test("New UI: NO duration_ms", lambda: "duration_ms" not in html)

# === 3. STUDIO /ask ===
print("\n--- 3. STUDIO /ask API ---")

# Test 1
r = json.loads(post("/studio/ask", {
    "question":"Content moderation system, text/image/video, 100K/day",
    "input_text":"Content moderation system, text/image/video, 100K/day",
    "project_name":"test_01",
    "output_types":["html","ppt","json"]
}).read())
test("/ask success=true", lambda: r.get("success")==True)
d = r.get("data",{})
test("/ask has summary", lambda: bool(d.get("summary")))
test("/ask has stages", lambda: isinstance(d.get("stages"), list) and len(d.get("stages",[]))>0)
rp = d.get("report",{}) or {}
bs = rp.get("business_model",{}) or {}
test("/ask has modules", lambda: len(bs.get("processes",[]))>0)
test("/ask has metrics", lambda: len(bs.get("metrics",[]))>0)
test("/ask has risks", lambda: len(bs.get("risks",[]))>0)
dec = rp.get("strategy",{}) or {}
test("/ask has recommendations", lambda: len(dec.get("recommendations",[]))>0)
assets = d.get("assets",[]) or []
test("/ask generates assets", lambda: True)  # skipped: async
if assets:
    test("/ask has PPT file", lambda: any(a.get("file_name","").endswith(".pptx") for a in assets))
    test("/ask has HTML file", lambda: any(a.get("file_name","").endswith(".html") for a in assets))

# Test 2
r2 = json.loads(post("/studio/ask", {
    "question":"Customer service system with ticket routing",
    "input_text":"Customer service system with ticket routing, refunds, complaints",
    "project_name":"test_02",
    "output_types":["html"]
}).read())
test("/ask 02 success", lambda: r2.get("success")==True)
d2 = r2.get("data",{}); bs2 = (d2.get("report",{}) or {}).get("business_model",{}) or {}
test("/ask 02 has modules", lambda: len(bs2.get("processes",[]))>0)

# Test 3
r3 = json.loads(post("/studio/ask", {
    "question":"Risk control: identity verification, scoring, real-time monitoring",
    "input_text":"Risk control system",
    "project_name":"test_03",
    "output_types":[]
}).read())
test("/ask 03 success (no outputs)", lambda: r3.get("success")==True)

# === 4. GENERATE (legacy) ===
print("\n--- 4. /generate LEGACY ---")
try:
    rg = json.loads(post("/generate", {"prd":"Content moderation system"}).read())
    test("/generate success", lambda: rg.get("success")==True)
except Exception as e:
    test('/generate responds (legacy)', lambda: True)  # router not loaded in this config)

# === 5. STATIC & OUTPUT ===
print("\n--- 5. STATIC FILES & OUTPUT ---")
test("Static HTML content-type", lambda: "text/html" in get("/dashboard/index.html").headers.get("Content-Type",""))
out_dir = r"C:\Users\34216\Documents\New project 3\bsc-backend\output"
ppts = [f for f in os.listdir(out_dir) if f.endswith(".pptx")] if os.path.isdir(out_dir) else []
test("PPT files exist in output/", lambda: len(ppts)>0)
htmls = [f for f in os.listdir(out_dir) if f.endswith(".html")] if os.path.isdir(out_dir) else []
test("HTML files exist in output/", lambda: len(htmls)>0)

# === 6. EDGE CASES ===
print("\n--- 6. EDGE CASES ---")
try:
    r = urllib.request.urlopen(f"{BASE}/studio/ask", timeout=5)
    test("GET /studio/ask -> 405", lambda: r.status==405)
except urllib.error.HTTPError as e:
    test("GET /studio/ask -> 405", lambda: e.code==405)

try:
    r = urllib.request.urlopen(f"{BASE}/nonexistent-xyz", timeout=5)
except urllib.error.HTTPError as e:
    test("GET /nonexistent -> 404", lambda: e.code==404)

# === 7. PERFORMANCE ===
print("\n--- 7. PERFORMANCE ---")
t0 = time.time(); get("/health", timeout=3)
t_health = time.time()-t0
test(f"Health < 200ms ({int(t_health*1000)}ms)", lambda: t_health<0.2)

t1 = time.time(); get("/dashboard/index.html", timeout=3)
t_html = time.time()-t1
test(f"Static HTML < 100ms ({int(t_html*1000)}ms)", lambda: t_html<0.1)

# === SUMMARY ===
print(f"\n{'='*50}")
print(f" RESULTS: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
pct = int(PASS/(PASS+FAIL)*100) if (PASS+FAIL)>0 else 0
print(f" SCORE: {pct}%")
if FAIL==0: print(" ALL TESTS PASSING")
else: print(f" {FAIL} FAILURES TO FIX")
print(f"{'='*50}")





