import argparse, json
from graph import build

p = argparse.ArgumentParser()
p.add_argument("--case", default="demo-1")
p.add_argument("--text", default="unauthorized card charge")
a = p.parse_args()
print(json.dumps(build().invoke({"case_id": a.case, "text": a.text}), indent=2))
