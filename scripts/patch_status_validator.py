import re, sys, pathlib

CANDIDATES = [pathlib.Path("app/schemas.py"), pathlib.Path("app/models.py")]
target = next((p for p in CANDIDATES if p.exists()), None)
if not target:
    print("!! Could not find app/schemas.py or app/models.py")
    sys.exit(1)

src = target.read_text(encoding="utf-8")

# Ensure imports
if "from pydantic import field_validator" not in src:
    if "from pydantic import BaseModel" in src:
        src = src.replace("from pydantic import BaseModel",
                          "from pydantic import BaseModel, field_validator")
    else:
        src = "from pydantic import BaseModel, field_validator\n" + src

# Inject BaseTaskModel with normalizer if missing
if "class BaseTaskModel(BaseModel):" not in src:
    inject = r'''
class BaseTaskModel(BaseModel):
    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v):
        if v is None:
            return v
        s = str(getattr(v, "value", v)).strip().lower()
        mapping = {
            "succeeded": "done",
            "success": "done",
            "completed": "done",
            "complete": "done",
            "failed": "error",
            "failure": "error",
            "fail": "error",
            "cancelled": "canceled",
        }
        return mapping.get(s, s)
'''
    # Put it after the last import block
    m = re.search(r"(^|\n)(?:from\s+\S+\s+import[^\n]*\n|import\s+\S+[^\n]*\n)+", src)
    if m:
        idx = m.end()
        src = src[:idx] + inject + src[idx:]
    else:
        src = inject + src

# Make Task-like models inherit BaseTaskModel instead of BaseModel
def repl_super(m):
    name = m.group(1)
    parents = m.group(2)
    if "BaseTaskModel" in parents:
        return m.group(0)  # already patched
    parents = parents.replace("BaseModel", "BaseTaskModel")
    return f"class {name}({parents}):"

src = re.sub(r"class\s+(Task\w*)\s*\(([^)]*)\):", repl_super, src)

target.write_text(src, encoding="utf-8")
print(f"Patched: {target}")
