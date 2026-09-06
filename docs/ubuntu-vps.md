# Ubuntu VPS deployment

This project can run the renderer in Docker so Graphviz, Cairo, Pango and fonts are fixed inside one Linux runtime instead of depending on the host workstation.

## Recommended host

Ubuntu 24.04 LTS or another current Ubuntu release with Docker Engine and the Docker Compose plugin.

Suggested application directory:

```bash
/opt/apps/historical-bloodlines-builder
```

## First deployment

Install Git and Docker using your normal server bootstrap process, then clone the repository:

```bash
sudo mkdir -p /opt/apps
sudo chown "$USER":"$USER" /opt/apps
cd /opt/apps
git clone https://github.com/shiaOmsword/historical-bloodlines-builder.git
cd historical-bloodlines-builder
```

Create the local Compose environment file and set the UID/GID of the account that owns the checkout:

```bash
cp .env.example .env
id -u
id -g
```

For the common Ubuntu first user both values are usually `1000`, which already matches `.env.example`. Change them if your server account uses different values.

Build the image:

```bash
docker compose build renderer
```

Run the full container smoke test:

```bash
sh scripts/docker_smoke.sh
```

A successful smoke test proves that the container can:

- start the Python application;
- find system `dot` and `neato`;
- load CairoSVG/Cairo/Pango;
- resolve the generic `Sans` font;
- read an `.xlsx` workbook;
- render publisher EPS;
- render the EPS preview PNG;
- compose a PDF.

## Rendering a real workbook

Copy the workbook into `data/input`:

```bash
cp /path/to/book.xlsx data/input/input.xlsx
```

Publisher EPS package plus preview PNG files:

```bash
docker compose run --rm renderer \
  -i /data/input/input.xlsx \
  -o /data/output/genealogy.eps
```

Multi-page PDF preview:

```bash
docker compose run --rm renderer \
  -i /data/input/input.xlsx \
  -o /data/output/genealogy.pdf
```

The host receives generated files under `data/output` because `./data` is mounted at `/data` in the container.

## Updating the server

```bash
cd /opt/apps/historical-bloodlines-builder
git checkout main
git pull --ff-only origin main
docker compose build renderer
sh scripts/docker_smoke.sh
```

Do not replace the smoke test with only `dot -V`: the important production path includes Cairo/Pango/font rendering and EPS conversion.

## Runtime model

The Docker image is intentionally CLI-first. It does not expose ports and does not require nginx, a domain, TLS, PostgreSQL or Redis.

The future Telegram bot should reuse the same application layer and renderer runtime. It can be added as a second Compose service without changing genealogy domain/rendering logic.

## Windows compatibility

The existing Windows portable Graphviz path is left intact. Docker uses the system Graphviz installed in the Linux image; Windows builds may continue using the bundled runtime as before.
