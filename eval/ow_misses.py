import json

d = json.load(open("eval/results/groq_openai_gpt-oss-120b.json"))
if isinstance(d, dict) and d and all(isinstance(v, dict) for v in d.values()):
    items = [{"id": k, **v} for k, v in d.items()]
elif isinstance(d, list):
    items = d
else:
    items = next(v for v in d.values() if isinstance(v, list))

print("fields:", list(items[0].keys()))
target = {"q15", "q20", "q39", "q40", "q41"}
for it in items:
    failed = any(v is False for v in it.values())
    if it.get("id") in target or failed:
        print("-----")
        print(json.dumps(it, indent=1, default=str)[:1500])