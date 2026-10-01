# Run

Build and start the service on port 8080 (from this `stage-1/` directory):

```sh
docker build -t pocketful-stage1 . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-stage1
```

Then `curl http://localhost:8080/health` returns `{"status":"ok"}`.

## Password storage
argon2id via Node 24 built-in crypto.argon2 (no outside package), m=47104 KiB, t=2, p=1, 16-byte random salt, 32-byte tag, PHC string. Reset fixtures with more than 64 users use the OWASP minimum m=19456 KiB, t=2, p=1 to fit the 10 s reset budget. Measured with docker --cpus=2 --memory=2g, 50 concurrent hashes: scrypt N=2^17 r=8 p=1 10196 ms, N=2^16 p=2 8709 ms, N=2^15 p=3 6683 ms, N=2^14 p=5 4943 ms (rejected: miss or have no margin to the 5 s per-request limit); argon2id m=19 MiB t=2 660 ms, m=46 MiB t=2 2380 ms (chosen), m=64 MiB t=2 3297 ms (rejected: too little margin). Service at e3f5e4a: 50 concurrent logins max 2478 ms, 50 concurrent signups max 2543 ms, 50-user reset 2395 ms, 150-user reset ~2 s.
