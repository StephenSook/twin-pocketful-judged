# Run

Build and start the service on port 8080 (from this `stage-1/` directory):

```sh
docker build -t pocketful-stage1 . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-stage1
```

Then `curl http://localhost:8080/health` returns `{"status":"ok"}`.
