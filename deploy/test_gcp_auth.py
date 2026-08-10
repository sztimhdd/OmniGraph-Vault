import google.auth
import google.auth.transport.requests
import os, time

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/root/.hermes/gcp-paid-sa.json"
t0 = time.time()
try:
    creds, project = google.auth.default()
    print(f"auth_method={type(creds).__name__} project={project} dt={time.time()-t0:.1f}s")
    request = google.auth.transport.requests.Request()
    t1 = time.time()
    creds.refresh(request)
    print(f"refresh_ok dt={time.time()-t1:.1f}s")
except Exception as e:
    print(f"auth_failed: {e}")
