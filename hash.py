import hashlib
def make_hash(p): return "sha256:" + hashlib.sha256(p.encode("utf-8")).hexdigest()
print(make_hash("1234"))
