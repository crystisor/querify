# Vane search service

The root `compose.yaml` runs Vane with a separate SearXNG service. This avoids
depending on the search adapters bundled in the older Vane image. SearXNG is
reachable only on the Compose network; Vane remains at http://localhost:3000.

The SearXNG image is pinned to the version verified for this setup. Its Google
CSE engine returned relevant results when the bundled service returned none.
Individual search providers can still rate-limit or block requests.

## Start

From the repository root, generate the ignored secret file once:

```powershell
if (-not (Test-Path .env.searxng)) {
    $secretBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $generator.GetBytes($secretBytes)
    $generator.Dispose()
    $searxSecret = ([BitConverter]::ToString($secretBytes)).Replace('-', '').ToLowerInvariant()
    "SEARXNG_SECRET=$searxSecret" | Set-Content -Encoding ascii .env.searxng
}
docker compose up -d
```

The external `vane-data` volume is the existing volume created by the original
`docker run` command. Compose reuses it so model settings and chat history persist.
On a new installation, create it with `docker volume create vane-data` first.
An existing standalone container named `vane` must be stopped and renamed before
the first Compose launch; retain it until the new setup is verified.

For an existing Vane installation, set **Settings > SearXNG URL** to
`http://searxng:8080`. Vane gives its saved URL priority over the environment
variable; the Compose variable supplies the default for new installations.

`settings.yml` enables JSON responses required by Vane. The server secret comes
from `.env.searxng`. The limiter is disabled for this private internal service.

## Check and update

```powershell
docker compose ps
docker compose logs --tail 50 searxng
```

Verify updates with a fresh Vane question and check both relevant sources and
the generated answer before changing the pinned image digest. Saved failed
answers are historical records and do not regenerate automatically.
