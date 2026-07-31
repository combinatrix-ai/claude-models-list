#!/usr/bin/env python3
"""Fetch Anthropic's public model catalog and update the repository artifacts.

The script deliberately uses only Python's standard library so the scheduled
workflow can run without installing dependencies.  It keeps the API response
shape (``data``, ``first_id``, ``last_id`` and ``has_more``) while adding a
small amount of provenance metadata for readers of the checked-in JSON file.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
from urllib.request import Request, urlopen


API_URL = "https://api.anthropic.com/v1/models"
API_DOCS_URL = "https://docs.anthropic.com/en/api/models-list"
API_VERSION = "2023-06-01"
DEFAULT_PAGE_SIZE = 100
MAX_PAGES = 100
BEGIN_MARKER = "<!-- BEGIN ANTHROPIC MODELS TABLE -->"
END_MARKER = "<!-- END ANTHROPIC MODELS TABLE -->"

UrlOpener = Callable[..., Any]


class APIError(RuntimeError):
    """A safe, user-facing error for failures talking to Anthropic."""


def _url_with_params(base_url: str, params: Mapping[str, str]) -> str:
    """Add query parameters without dropping any already present in a URL."""

    parsed = urlparse(base_url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend(params.items())
    return urlunparse(parsed._replace(query=urlencode(query)))


def _request_json(
    url: str,
    api_key: str,
    *,
    timeout: float,
    opener: UrlOpener = urlopen,
) -> dict[str, Any]:
    """Request and decode one page, without ever including the API key in errors."""

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "combinatrix-ai/claude-models-list",
            "anthropic-version": API_VERSION,
            "x-api-key": api_key,
        },
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        # Do not echo the response body: an upstream proxy could include
        # request metadata, and the API key must never appear in logs.
        raise APIError(f"Anthropic Models API request failed (HTTP {exc.code})") from exc
    except URLError as exc:
        raise APIError("Could not reach the Anthropic Models API") from exc
    except OSError as exc:
        raise APIError("Could not read the Anthropic Models API response") from exc

    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APIError("Anthropic Models API returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise APIError("Anthropic Models API returned an unexpected JSON shape")
    return decoded


def fetch_models(
    api_key: str,
    *,
    api_url: str = API_URL,
    page_size: int = DEFAULT_PAGE_SIZE,
    timeout: float = 30.0,
    opener: UrlOpener = urlopen,
) -> dict[str, Any]:
    """Fetch every available model, following ``after_id`` pagination."""

    if not api_key:
        raise APIError("An Anthropic API key is required")
    if not 1 <= page_size <= 1000:
        raise APIError("page_size must be between 1 and 1000")

    all_models: list[dict[str, Any]] = []
    first_page: dict[str, Any] | None = None
    next_after_id: str | None = None
    seen_ids: set[str] = set()

    for page_number in range(1, MAX_PAGES + 1):
        params: dict[str, str] = {"limit": str(page_size)}
        if next_after_id:
            params["after_id"] = next_after_id
        page = _request_json(
            _url_with_params(api_url, params),
            api_key,
            timeout=timeout,
            opener=opener,
        )
        if first_page is None:
            first_page = page

        page_data = page.get("data")
        if not isinstance(page_data, list):
            raise APIError("Anthropic Models API response has no model data array")
        for model in page_data:
            if not isinstance(model, dict) or not isinstance(model.get("id"), str):
                raise APIError("Anthropic Models API returned a model without a string id")
            model_id = model["id"]
            if model_id in seen_ids:
                raise APIError(f"Anthropic Models API returned duplicate model id: {model_id}")
            seen_ids.add(model_id)
            all_models.append(model)

        has_more = page.get("has_more", False)
        if not isinstance(has_more, bool):
            raise APIError("Anthropic Models API returned a non-boolean has_more")
        if not has_more:
            last_id = page.get("last_id")
            if last_id is None and all_models:
                last_id = all_models[-1]["id"]
            return {
                "data": all_models,
                "first_id": (first_page or {}).get("first_id"),
                "last_id": last_id,
                "has_more": False,
            }

        last_id = page.get("last_id")
        if not isinstance(last_id, str) or not last_id:
            raise APIError("Anthropic Models API indicated another page without last_id")
        if last_id == next_after_id:
            raise APIError("Anthropic Models API pagination did not advance")
        next_after_id = last_id

    raise APIError(f"Anthropic Models API exceeded the {MAX_PAGES}-page safety limit")


def utc_now() -> str:
    """Return a compact, stable UTC timestamp for generated artifacts."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_document(response: Mapping[str, Any], retrieved_at: str) -> dict[str, Any]:
    """Add provenance while retaining the API's model-list fields."""

    return {
        "source": {
            "name": "Anthropic Models API",
            "endpoint": API_URL,
            "documentation": API_DOCS_URL,
        },
        "retrieved_at": retrieved_at,
        "data": response.get("data", []),
        "first_id": response.get("first_id"),
        "last_id": response.get("last_id"),
        "has_more": response.get("has_more", False),
    }


def write_json(path: Path, document: Mapping[str, Any]) -> None:
    """Write JSON atomically, avoiding half-written public data on interruption."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _cell(value: Any) -> str:
    text = "—" if value is None or value == "" else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _date(value: Any) -> str:
    if not isinstance(value, str):
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d")


def _number(value: Any) -> str:
    if isinstance(value, bool):
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def render_table(document: Mapping[str, Any]) -> str:
    """Render the generated README section from a models document."""

    models = document.get("data", [])
    if not isinstance(models, list):
        raise ValueError("models document data must be a list")
    retrieved_at = _cell(document.get("retrieved_at"))
    lines = [
        BEGIN_MARKER,
        f"Last refreshed: `{retrieved_at}` (UTC).",
        "",
        "| Model | Model ID | Created | Max input tokens | Max output tokens |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for model in models:
        if not isinstance(model, Mapping):
            continue
        lines.append(
            "| "
            + " | ".join(
                (
                    _cell(model.get("display_name") or model.get("id")),
                    f"`{_cell(model.get('id'))}`",
                    _date(model.get("created_at")),
                    _number(model.get("max_input_tokens")),
                    _number(model.get("max_tokens")),
                )
            )
            + " |"
        )
    lines.extend((END_MARKER,))
    return "\n".join(lines)


def update_readme(path: Path, document: Mapping[str, Any]) -> None:
    """Replace only the marked model table section in README.md."""

    content = path.read_text(encoding="utf-8")
    start = content.find(BEGIN_MARKER)
    end_marker_start = content.find(END_MARKER, start + len(BEGIN_MARKER)) if start >= 0 else -1
    if start < 0 or end_marker_start < 0:
        raise ValueError(f"README is missing {BEGIN_MARKER} / {END_MARKER}")
    end = end_marker_start + len(END_MARKER)
    replacement = render_table(document)
    path.write_text(content[:start] + replacement + content[end:], encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models.json"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--api-key-env", default="ANTHROPIC_API_KEY")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is not set")
    try:
        response = fetch_models(
            api_key,
            api_url=args.api_url,
            page_size=args.page_size,
            timeout=args.timeout,
        )
        document = build_document(response, utc_now())
        write_json(args.output, document)
        update_readme(args.readme, document)
    except (APIError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    count = len(document["data"])
    print(f"Updated {args.output} and {args.readme} ({count} models; retrieved at {document['retrieved_at']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
