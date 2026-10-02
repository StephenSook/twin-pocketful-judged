# Live demo

The public demo runs the band's last stage folder, built unchanged from its own Dockerfile, behind
a small front door (`proxy.py`, standard library only):

- `/_test/*` answers 404. The spec leaves reset, export and import unauthenticated, which is right
  for a test harness and wrong for a public URL.
- The connection address is rate limited (120 requests per 10 seconds) and bodies are capped at 1 MiB.
- Every hour the front door reseeds the service from `seed.json` through the service's own reset
  endpoint, so the demo accounts always work. `/__demo/status` shows the last reseed.
- Responses are passed through unchanged, including the service's own security headers.

Demo logins (all use the password `pocketful demo`): `ada@demo.example`, `bob@demo.example`,
`cleo@demo.example`, `dev@demo.example`. Anyone can also sign up; the hourly reseed clears it.

Build and run locally:

```
docker build -t app stage-4
APP_ARGV_B64="<base64 JSON array from the built image's Entrypoint plus Cmd>"
docker build -t demo --build-arg APP_IMAGE=app --build-arg APP_ARGV_B64="$APP_ARGV_B64" deploy
docker run --rm -p 10000:10000 demo
```

The `demo-image` workflow does the same in CI, smoke tests it, and publishes the image to the GitHub
container registry for the host to pull.

Host on Render's free plan (the judged demo runs here):

- New web service from this public repository, runtime Docker, Dockerfile path
  `deploy/render.Dockerfile`, build context `deploy`, health check `/health`, one instance,
  auto-deploy off.
- Service variable `DEMO_IMAGE` set to the immutable tag the `demo-image` workflow published for
  the commit being deployed (`ghcr.io/<owner>/<repo>-demo:<first 12 characters of the commit>`).
  Render passes service variables to Docker builds as build arguments.
- A free instance sleeps after about 15 idle minutes. The first request after that takes about a
  minute while it starts, and the front door reseeds the demo accounts on start.
