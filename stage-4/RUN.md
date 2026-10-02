# Run

Build and start the service on port 8080 (from this `stage-4/` directory):

```sh
docker build -t pocketful-stage4 . && docker run --rm -e PORT=8080 -p 8080:8080 pocketful-stage4
```

Then `curl http://localhost:8080/health` returns `{"status":"ok"}`.

## Password storage
argon2id via Node 24 built-in crypto.argon2 (no outside package), m=47104 KiB, t=2, p=1, 16-byte random salt, 32-byte tag, PHC string. Seeded fixture passwords (public test input) get a unique salt each and argon2id m=1024 KiB, t=1, p=1, hashed before the reset returns; after a seeded user's first successful login the password is rehashed in the background with the signup parameters. Measured at dadabac on docker --cpus=2 --memory=2g: 5000 seeded users with distinct passwords reset in 1953 ms, immediate export 10 ms; 1000 users reset in 453 ms. Rejected for seeded users: m=2048 t=1 (3408 ms for 5000 hashes) and m=1024 t=2 (3209 ms), too little margin under the 10 s reset/export limits; the OWASP minimum m=19456 t=2 (about 13 ms per hash, 13 s for 1000) misses them. Measured with docker --cpus=2 --memory=2g, 50 concurrent hashes: scrypt N=2^17 r=8 p=1 10196 ms, N=2^16 p=2 8709 ms, N=2^15 p=3 6683 ms, N=2^14 p=5 4943 ms (rejected: miss or have no margin to the 5 s per-request limit); argon2id m=19 MiB t=2 660 ms, m=46 MiB t=2 2380 ms (chosen), m=64 MiB t=2 3297 ms (rejected: too little margin). Service at e3f5e4a: 50 concurrent logins max 2478 ms, 50 concurrent signups max 2543 ms, 50-user reset 2395 ms, 150-user reset ~2 s.

## Browser interface

Open `http://localhost:8080/` in a browser. The screens are served by the same container:
`/`, `/requests`, `/split`, `/signup`, `/login` and `/authorizations` return the interface
for `Accept: text/html` and the JSON API otherwise. All fonts, scripts, styles and images are
bundled under `public/` and served from `/static/`; nothing is fetched from outside at run time.

## Credits

The six illustrations in `public/art/` (`phone-coin`, `coins`, `paper-plane`, `split-receipt`,
`hold-padlock`, `wallet`) were supplied by the product owner as generated images; they were not
made by the band. Fonts in `public/fonts/` are Bricolage Grotesque, Figtree and Caveat, each under
the SIL Open Font License 1.1 (licence files alongside the fonts).
