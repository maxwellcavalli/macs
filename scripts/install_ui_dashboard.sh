#!/usr/bin/env bash
set -euo pipefail

# --- Write app/ui.py ---
cat > app/ui.py <<'PY'
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"], include_in_schema=False)

DASHBOARD_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>MACS Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-gray-100">
  <div class="max-w-6xl mx-auto p-6 space-y-6">
    <header class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold">MACS Dashboard</h1>
      <button id="refreshBtn" class="px-3 py-2 rounded-2xl bg-gray-800 hover:bg-gray-700">Refresh</button>
    </header>
    <div id="alerts"></div>
    <section class="grid md:grid-cols-3 gap-4">
      <div class="p-4 rounded-2xl bg-gray-900 shadow">
        <h2 class="text-lg font-medium mb-2">Ollama Health</h2>
        <pre id="health" class="text-sm whitespace-pre-wrap"></pre>
      </div>
      <div class="p-4 rounded-2xl bg-gray-900 shadow">
        <h2 class="text-lg font-medium mb-2">Models</h2>
        <pre id="models" class="text-sm whitespace-pre-wrap"></pre>
      </div>
      <div class="p-4 rounded-2xl bg-gray-900 shadow">
        <h2 class="text-lg font-medium mb-2">Rate Limit</h2>
        <pre id="ratelimit" class="text-sm whitespace-pre-wrap"></pre>
      </div>
    </section>
    <section class="p-4 rounded-2xl bg-gray-900 shadow">
      <h2 class="text-lg font-medium mb-2">Prometheus</h2>
      <p class="text-sm">If metrics are enabled, scrape at <code>/metrics</code> and graph in Grafana.</p>
    </section>
    <footer class="text-xs text-gray-400">Updated <span id="updatedAt">—</span></footer>
  </div>
  <script>
    async function get(path){
      const res = await fetch(path);
      if(!res.ok) throw new Error(path + " → " + res.status + " " + res.statusText);
      return res.json();
    }
    function setPre(id, obj){
      document.getElementById(id).textContent = JSON.stringify(obj, null, 2);
    }
    function setAlert(msg, ok=true){
      const el = document.getElementById('alerts');
      el.innerHTML = '';
      if(!msg) return;
      const div = document.createElement('div');
      div.className = 'rounded-xl p-3 ' + (ok ? 'bg-emerald-900/40 border border-emerald-600/30' : 'bg-red-900/40 border border-red-600/30');
      div.textContent = msg;
      el.appendChild(div);
    }
    async function refresh(){
      try {
        const [health, models, rl] = await Promise.all([
          get('/v1/ollama/health'),
          get('/v1/models?debug=1'),
          get('/v1/ratelimit/check?consume=0'),
        ]);
        setPre('health', health);
        setPre('models', models);
        setPre('ratelimit', rl);
        setAlert('OK');
      } catch (e){
        setAlert('Error: ' + e.message, false);
      } finally {
        document.getElementById('updatedAt').textContent = new Date().toLocaleString();
      }
    }
    document.getElementById('refreshBtn').addEventListener('click', refresh);
    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""
@router.get("/ui", response_class=HTMLResponse)
def ui_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)
PY

# --- Ensure imports and router wiring in app/main.py ---
if ! grep -q 'from app.ui import router as ui_router' app/main.py; then
  awk 'BEGIN{done=0} !done && /^from app\.api import router as api_router/ {print; print "from app.ui import router as ui_router"; done=1; next} {print}' app/main.py > app/main.py.new && mv app/main.py.new app/main.py
fi
if ! grep -q 'app.include_router(ui_router)' app/main.py; then
  awk 'BEGIN{done=0} !done && /app\.include_router\(api_router, *prefix *= *"\/v1"\)/ {print; print "app.include_router(ui_router)"; done=1; next} {print}' app/main.py > app/main.py.new && mv app/main.py.new app/main.py
fi

# --- Add /v1/ui fallback to app/api.py (non-breaking) ---
if ! grep -q 'from fastapi.responses import HTMLResponse' app/api.py; then
  awk 'BEGIN{done=0} !done && /^from fastapi import APIRouter/ {print; print "from fastapi.responses import HTMLResponse"; done=1; next} {print}' app/api.py > app/api.py.new && mv app/api.py.new app/api.py
fi
if ! grep -q 'def ui_fallback' app/api.py; then
  cat >> app/api.py <<'PY'
# --- UI fallback under /v1 for convenience ---
try:
    from app.ui import DASHBOARD_HTML
    @router.get("/ui", include_in_schema=False, response_class=HTMLResponse)
    def ui_fallback():
        return HTMLResponse(content=DASHBOARD_HTML)
except Exception:
    pass
PY
fi

echo "OK: UI installed. Commit with: git add -A && git commit -m 'ui: add minimal /ui dashboard and /v1/ui fallback'"
