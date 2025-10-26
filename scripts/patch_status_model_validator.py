import re, sys, pathlib

candidates = [pathlib.Path("app/schemas.py"), pathlib.Path("app/models.py")]
target = next((p for p in candidates if p.exists()), None)
if not target:
    print("!! Could not find app/schemas.py or app/models.py")
    sys.exit(1)

src = target.read_text(encoding="utf-8")

# Ensure imports include model_validator
if "model_validator" not in src:
    if re.search(r"\nfrom\s+pydantic\s+import\s+([^\n]+)\n", src):
        def add_mv(m):
            items = [x.strip() for x in m.group(1).split(",")]
            if "model_validator" not in items:
                items.append("model_validator")
            return f"\nfrom pydantic import {', '.join(sorted(set(items)))}\n"
        src = re.sub(r"\nfrom\s+pydantic\s+import\s+([^\n]+)\n", add_mv, src, count=1)
    else:
        src = "from pydantic import BaseModel, model_validator\n" + src

# Rename any existing BaseTaskModel to avoid duplicate class names
src, n_ren = re.subn(r"^(\s*)class\s+BaseTaskModel\b", r"\1class _OldBaseTaskModel", src, flags=re.M)

# Build new BaseTaskModel using model_validator
new_base = r'''
class BaseTaskModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _normalize_status(cls, data):
        try:
            if isinstance(data, dict) and "status" in data:
                raw = data["status"]
                s = str(getattr(raw, "value", raw)).strip().lower()
                mapping = {
                    "succeeded": "done",
                    "success":   "done",
                    "completed": "done",
                    "complete":  "done",
                    "failed":    "error",
                    "failure":   "error",
                    "fail":      "error",
                    "cancelled": "canceled",
                }
                data["status"] = mapping.get(s, s)
        except Exception:
            # best-effort only; never block model construction
            pass
        return data
'''

# Insert new base model after last import
m = list(re.finditer(r"^(?:from\s+\S+\s+import[^\n]*|import\s+\S+[^\n]*)\n", src, flags=re.M))
insert_at = m[-1].end() if m else 0
src = src[:insert_at] + new_base + src[insert_at:]

# Make Task* models inherit BaseTaskModel instead of BaseModel
def repl_task_parent(mm):
    name, parents = mm.group(1), mm.group(2)
    if "BaseTaskModel" in parents:
        return mm.group(0)
    parents = re.sub(r"\bBaseModel\b", "BaseTaskModel", parents)
    return f"class {name}({parents}):"

src, n_task = re.subn(r"^class\s+(Task\w*)\s*\(([^)]*)\):", repl_task_parent, src, flags=re.M)

target.write_text(src, encoding="utf-8")
print(f"Patched {target} (renamed BaseTaskModel: {n_ren}, Task* parents updated: {n_task})")
