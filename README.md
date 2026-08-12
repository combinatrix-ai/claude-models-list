# Claude Models List

An automatically refreshed list of model IDs available to this repository's
Anthropic API account. The data is fetched from Anthropic's official
[`GET /v1/models` endpoint](https://docs.anthropic.com/en/api/models-list) once
per day by GitHub Actions and committed as public JSON.

Anthropic's Models API requires an API key. This repository exists as a
read-only public mirror for environments where an Anthropic API key is not
available or should not be distributed. It is a periodically refreshed
snapshot, not a proxy for the Anthropic API.

## Current models

The generated table below is intentionally limited to fields returned by the
API. This project does not infer lifecycle, deprecation, retirement, or
successor claims that Anthropic has not included in the response.

<!-- BEGIN ANTHROPIC MODELS TABLE -->
Last refreshed: `2026-08-12T02:47:40Z` (UTC).

| Model | Model ID | Created | Max input tokens | Max output tokens |
| --- | --- | --- | ---: | ---: |
| Claude Opus 5 | `claude-opus-5` | 2026-07-24 | 1,000,000 | 128,000 |
| Claude Sonnet 5 | `claude-sonnet-5` | 2026-06-29 | 1,000,000 | 128,000 |
| Claude Fable 5 | `claude-fable-5` | 2026-06-07 | 1,000,000 | 128,000 |
| Claude Opus 4.8 | `claude-opus-4-8` | 2026-05-28 | 1,000,000 | 128,000 |
| Claude Opus 4.7 | `claude-opus-4-7` | 2026-04-14 | 1,000,000 | 128,000 |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | 2026-02-17 | 1,000,000 | 128,000 |
| Claude Opus 4.6 | `claude-opus-4-6` | 2026-02-04 | 1,000,000 | 128,000 |
| Claude Opus 4.5 | `claude-opus-4-5-20251101` | 2025-11-24 | 200,000 | 64,000 |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | 2025-10-15 | 200,000 | 64,000 |
| Claude Sonnet 4.5 | `claude-sonnet-4-5-20250929` | 2025-09-29 | 1,000,000 | 64,000 |
<!-- END ANTHROPIC MODELS TABLE -->

## Machine-readable data

- [`models.json`](models.json) — the latest API response, with `data` containing the model objects.
- [Raw `models.json`](https://raw.githubusercontent.com/combinatrix-ai/claude-models-list/main/models.json) — convenient for scripts and shell pipelines.
- [Anthropic Models API documentation](https://docs.anthropic.com/en/api/models-list) — the authoritative source.

The JSON includes `source`, `retrieved_at`, `data`, `first_id`, `last_id`, and
`has_more`. Each model object is retained as returned by Anthropic, including
its `id`, `display_name`, `created_at`, and any additional fields exposed by the
API. The checked-in snapshot is account-scoped: it represents models available
to the API key used by the updater, not every model Anthropic has ever
published.

## Usage

List model IDs with `curl` and `jq`:

```sh
curl -fsSL https://raw.githubusercontent.com/combinatrix-ai/claude-models-list/main/models.json \
  | jq -r '.data[].id'
```

Read the snapshot from Python:

```python
import json
from urllib.request import urlopen

with urlopen(
    "https://raw.githubusercontent.com/combinatrix-ai/claude-models-list/main/models.json"
) as response:
    models = json.load(response)["data"]

for model in models:
    print(model["id"], "—", model["display_name"])
```

To query Anthropic directly, keep your key in an environment variable rather
than putting it in a command, script, or public file:

```sh
curl -fsSL https://api.anthropic.com/v1/models?limit=100 \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01"
```

## Updates

`.github/workflows/update-models.yml` runs daily and can also be started with
**Run workflow**. It uses the `ANTHROPIC_API_KEY` GitHub Actions secret, follows
the API's cursor pagination, regenerates `models.json` and this marked README
section, then commits only when the content changes. The workflow is not
triggered by pull requests and grants only `contents: write` permission.

For a local refresh:

```sh
ANTHROPIC_API_KEY=... python3 scripts/update_models.py
python3 -m unittest discover -s tests -v
```

## License

This project is released under the [MIT License](LICENSE). Anthropic model
names, IDs, and API response fields remain subject to Anthropic's terms and
documentation.
