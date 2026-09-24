from pathlib import Path
import subprocess

ROOT = Path(".")
TEXT_EXTS = {".py", ".yml", ".yaml", ".md", ".txt"}

def git_mv(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "mv", str(src), str(dst)], check=True)

def classify(name: str):
    if name == "bench_silesia.py":
        return Path("benchmarks/silesia") / name
    if name in {"full_compressor_benchmark.py", "exp48_competitor_benchmark.py"}:
        return Path("benchmarks/competitors") / name
    if name.startswith("make_exp"):
        return Path("research/generators/general") / name
    if name.startswith("make_fast") or name.startswith("make_speed"):
        return Path("research/generators/speed") / name
    if name.startswith("exp"):
        if "validate" in name:
            return Path("research/validation") / name
        if "oracle" in name:
            return Path("research/oracles") / name
        if "router" in name:
            return Path("research/routers") / name
        if "diagnostic" in name or "inspect" in name:
            return Path("research/diagnostics") / name
        return Path("research/experiments") / name
    if name.startswith("fast") or name.startswith("speed") or name.startswith("speedd"):
        return Path("research/speed") / name
    return None

mapping = {}

src_parts = ROOT / "source_parts"
if src_parts.exists():
    dst = ROOT / "engine/source_parts"
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "mv", str(src_parts), str(dst)], check=True)
    mapping["source_parts/"] = "engine/source_parts/"

for p in sorted(ROOT.glob("*.py")):
    dst = classify(p.name)
    if dst is None:
        continue
    mapping[p.name] = dst.as_posix()
    git_mv(p, dst)

for p in ROOT.rglob("*"):
    if not p.is_file() or ".git" in p.parts or p.suffix.lower() not in TEXT_EXTS:
        continue
    try:
        text = p.read_text()
    except UnicodeDecodeError:
        continue
    new = text
    for old, repl in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        new = new.replace(old, repl)
    if new != text:
        p.write_text(new)

readme = """# AURORA Compressor / KEPHIR

This branch contains the general-purpose file compression project.

Branch identity:
- Product: AURORA Compressor
- Compression engine: KEPHIR
- Scope: files, archives, Silesia research, ratio/speed experiments, routers and validation
- Canonical branch: project/aurora-compressor

The audio/video codec project is maintained separately on project/aurora-media.

Repository layout:

engine/
  source_parts/              canonical encoded source fragments used to rebuild KEPHIR baselines

research/
  experiments/               EXP chronological experiments and sweeps
  validation/                promoted-checkpoint validation scripts
  oracles/                   oracle/research upper-bound experiments
  routers/                   structural/adaptive routing research
  diagnostics/               inspection/profiling/diagnostic experiments
  generators/general/        make_exp source generators
  generators/speed/          make_fast and make_speed generators
  speed/                     FAST/SPEED benchmarks and A/B measurements

benchmarks/
  silesia/                   canonical Silesia benchmark harness
  competitors/               comparisons against external compressors

docs/architecture/           project map and file catalog
.github/workflows/           CI and reproducibility workflows
tools/maintenance/           repository-maintenance scripts

Project rule:
AURORA Compressor and AURORA Media share KEPHIR concepts and lineage, but product-specific research must not be mixed in the same working branch.
"""
Path("README.md").write_text(readme)

arch = Path("docs/architecture")
arch.mkdir(parents=True, exist_ok=True)
(arch/"PROJECT_STRUCTURE.md").write_text("""# AURORA Compressor — Canonical Structure

## Product boundary

This branch is exclusively for general-purpose file/archive compression.

Media-specific audio/video/container/streaming work belongs to project/aurora-media.

## Categories

- engine/source_parts/: reconstructable KEPHIR source fragments.
- research/experiments/: chronological EXP research.
- research/validation/: reproducibility checks for named checkpoints.
- research/oracles/: non-production upper-bound experiments.
- research/routers/: structural routing research.
- research/diagnostics/: profiling and inspection.
- research/generators/general/: generators that synthesize EXP C++ sources.
- research/generators/speed/: generators for FAST/SPEED C++ sources.
- research/speed/: runtime speed experiments and A/B harnesses.
- benchmarks/silesia/: canonical corpus benchmark.
- benchmarks/competitors/: external-compressor comparisons.
- .github/workflows/: CI only; workflow names retain experiment identity for reproducibility.

## Naming rule

Historical experiment IDs (EXP-xx, FAST-x) are retained in filenames. Location now defines role; filename defines experiment identity.
""")

catalog = ["# AURORA Compressor — File Catalog", "", "Generated by repository migration.", ""]
for folder in [
    "engine/source_parts",
    "research/experiments",
    "research/validation",
    "research/oracles",
    "research/routers",
    "research/diagnostics",
    "research/generators/general",
    "research/generators/speed",
    "research/speed",
    "benchmarks/silesia",
    "benchmarks/competitors",
]:
    catalog += [f"## {folder}", ""]
    base = Path(folder)
    files = sorted(p.as_posix() for p in base.rglob("*") if p.is_file()) if base.exists() else []
    catalog += [f"- {x}" for x in files] or ["- empty"]
    catalog.append("")
(arch/"FILE_CATALOG.md").write_text("\n".join(catalog))

left = sorted(p.name for p in ROOT.glob("*.py"))
if left:
    raise SystemExit("UNCLASSIFIED_ROOT_PY: " + ", ".join(left))

print("MOVED_REFERENCES", len(mapping))
print("AURORA_COMPRESSOR_REORGANIZATION_OK")
