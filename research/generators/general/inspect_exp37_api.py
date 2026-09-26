from pathlib import Path
import re

p=Path("KEPHIR_2_EXP37_DUAL_MATCH.cpp")
s=p.read_text()
lines=s.splitlines()

print("EXP37_TOTAL_LINES",len(lines))
print("EXP37_TOTAL_BYTES",len(s.encode()))

sig_re=re.compile(
    r"^\s*(?:static\s+)?(?:int|void|bool|vector<[^>]+>|[A-Za-z_][\w:<>]*)\s+"
    r"([A-Za-z_]\w*)\s*\([^;]*\)\s*\{\s*$"
)

print("EXP37_FUNCTION_SIGNATURES_BEGIN")
for i,line in enumerate(lines,1):
    m=sig_re.match(line)
    if m:
        print(f"{i}: {line.strip()}")
print("EXP37_FUNCTION_SIGNATURES_END")

main_line=None
for i,line in enumerate(lines):
    if re.search(r"\bint\s+main\s*\(",line):
        main_line=i
        break

if main_line is None:
    raise SystemExit("main not found")

start=max(0,main_line-20)
end=min(len(lines),main_line+220)
print("EXP37_MAIN_CONTEXT_BEGIN")
for i in range(start,end):
    print(f"{i+1}: {lines[i]}")
print("EXP37_MAIN_CONTEXT_END")


print("EXP37_CORE_CONTEXT_BEGIN")
for i in range(690,min(len(lines),920)):
    print(f"{i+1}: {lines[i]}")
print("EXP37_CORE_CONTEXT_END")
