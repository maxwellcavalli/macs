import json
from typing import Dict, List, Tuple
from starlette.types import ASGIApp, Receive, Scope, Send

try:
    from .status_norm import norm_payload
except Exception:
    def norm_payload(x): return x

def _h2d(h: List[Tuple[bytes,bytes]]) -> Dict[str,str]:
    return {k.decode().lower(): v.decode() for k,v in h}
def _d2h(d: Dict[str,str]) -> List[Tuple[bytes,bytes]]:
    return [(k.encode(), v.encode()) for k,v in d.items()]

class JSONCanonicalizerMiddleware:
    def __init__(self, app: ASGIApp) -> None: self.app = app
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
      if scope.get("type")!="http": return await self.app(scope,receive,send)
      defer={"on":False,"status":200,"headers":[]}; chunks: List[bytes]=[]
      async def send_wrapper(ev):
        if ev["type"]=="http.response.start":
          hd=_h2d(ev.get("headers",[]))
          if "application/json" in (hd.get("content-type") or "").lower():
            defer.update(on=True,status=ev["status"],headers=ev["headers"]); return
          return await send(ev)
        if ev["type"]=="http.response.body" and defer["on"]:
          chunks.append(ev.get("body",b""))
          if ev.get("more_body"): return
          raw=b"".join(chunks)
          try:
            data=norm_payload(json.loads(raw.decode("utf-8"))); body=json.dumps(data,ensure_ascii=False).encode("utf-8")
          except Exception:
            body=raw
          hd=_h2d(defer["headers"]); hd.pop("content-length",None)
          await send({"type":"http.response.start","status":defer["status"],"headers":_d2h(hd)})
          await send({"type":"http.response.body","body":body,"more_body":False}); return
        return await send(ev)
      await self.app(scope,receive,send_wrapper)

class SSECanonicalizerMiddleware:
    """
    Rewrites 'data: <json>' payloads to canonical and ensures termination.
    Treats status=='timeout' as terminal -> maps to error+note=timeout, appends [DONE], closes.
    Set SSE_CANON_MODE=off to bypass.
    """
    def __init__(self, app: ASGIApp) -> None: self.app = app
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
      if scope.get("type")!="http": return await self.app(scope,receive,send)
      import os
      if (os.getenv("SSE_CANON_MODE","on") or "on").lower() in ("off","0","false","disabled"):
        return await self.app(scope,receive,send)
      is_sse={"v":False}; buf={"s":""}; closed={"v":False}
      async def send_wrapper(ev):
        if closed["v"]: return
        if ev["type"]=="http.response.start":
          hd=_h2d(ev.get("headers",[]))
          is_sse["v"]="text/event-stream" in (hd.get("content-type") or "").lower()
          if is_sse["v"]:
            hd.setdefault("cache-control","no-cache"); hd.setdefault("x-accel-buffering","no")
            e=dict(ev); e["headers"]=_d2h(hd); return await send(e)
          return await send(ev)
        if ev["type"]=="http.response.body" and is_sse["v"]:
          chunk=ev.get("body",b"").decode("utf-8","ignore"); more_up=bool(ev.get("more_body",False))
          buf["s"]+=chunk
          parts=buf["s"].split("\n\n"); buf["s"]=parts.pop() if more_up else ""
          out: List[str]=[]
          saw_terminal=False; saw_done_marker=False
          for evtxt in parts:
            if evtxt.startswith("data:"):
              payload=evtxt[5:].lstrip()
              if payload=="[DONE]":
                out.append("data: [DONE]\n\n"); saw_terminal=True; saw_done_marker=True
              else:
                try:
                  obj=json.loads(payload)
                  # canonicalize nested fields
                  obj=norm_payload(obj)
                  st=str(obj.get("status","")).lower()
                  if st=="timeout":  # map timeout => error for clients
                    obj["status"]="error"; obj.setdefault("note","timeout"); saw_terminal=True
                  if st in ("done","error","canceled") or str(obj.get("note","")).lower()=="artifacts-present":
                    saw_terminal=True
                  out.append("data: "+json.dumps(obj,ensure_ascii=False)+"\n\n")
                except Exception:
                  out.append(evtxt+"\n\n")
            else:
              out.append(evtxt+"\n\n")
          if saw_terminal:
            if not saw_done_marker:
              out.append("data: [DONE]\n\n")
            data="".join(out).encode("utf-8")
            await send({"type":"http.response.body","body":data,"more_body":False})
            closed["v"]=True
            return
          data="".join(out).encode("utf-8")
          return await send({"type":"http.response.body","body":data,"more_body":more_up})
        return await send(ev)
      await self.app(scope,receive,send_wrapper)
