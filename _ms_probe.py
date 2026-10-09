import sys

try:
    import modelscope
    print("modelscope", modelscope.__version__)
except Exception as e:
    print("NO_MODELSCOPE", repr(e))
    sys.exit(0)

from modelscope.hub.api import HubApi

api = HubApi()
for rid in ["jaredpalmer/kev-0.8b", "jaredpalmer/kev-0.8B", "kev-0.8b/kev-0.8b"]:
    try:
        info = api.get_model(rid)
        print("EXISTS", rid, type(info))
        break
    except Exception as e:
        print("MISSING", rid, repr(e)[:200])
