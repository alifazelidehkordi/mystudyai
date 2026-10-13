"""Wikimedia Commons image discovery with attribution and opt-in local insertion.

No lecture text is uploaded. Images are candidate illustrations, never medically
verified. License metadata is filtered conservatively and must be reviewed.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "MyStudyAI/0.3 (education; Wikimedia Commons and NCBI public APIs)"
MAX_IMAGE_BYTES = 8_000_000
MIMES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class ImageSearchError(RuntimeError):
    pass


class _PlainHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain(value: str) -> str:
    parser = _PlainHTML()
    parser.feed(str(value))
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()[:350]


def allowed_license(name: str) -> bool:
    """Only known open license families, not NC/ND or unspecified files."""
    norm = re.sub(r"\s+", " ", name.replace("_", " ")).strip().casefold()
    return bool(
        re.fullmatch(r"cc[ -]?by(?:[ -]?sa)?[ -]?\d+(?:\.\d+)?", norm)
        or re.fullmatch(r"cc0(?:[ -]?\d+(?:\.\d+)?)?", norm)
        or norm in {"public domain", "pd"}
    )


@dataclass(frozen=True)
class CommonsImage:
    title: str
    file_page: str
    thumbnail: str
    author: str
    license_name: str
    license_url: str
    mime: str
    description: str


def _json_get(url: str) -> dict:
    try:
        with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as reply:
            raw = reply.read(2_000_001)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ImageSearchError("Could not reach Wikimedia Commons.") from None
    if len(raw) > 2_000_000:
        raise ImageSearchError("The image search response was too large.")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise ImageSearchError("Wikimedia Commons returned invalid JSON.") from None
    if not isinstance(value, dict) or "error" in value:
        raise ImageSearchError("Wikimedia Commons rejected the image search.")
    return value


def search_commons(topic: str, limit: int = 6) -> list[CommonsImage]:
    """Return attribution-ready Commons image candidates; remote search only."""
    if not topic.strip() or len(topic) > 180:
        raise ValueError("Use a non-empty image topic of at most 180 characters.")
    if not 1 <= limit <= 15:
        raise ValueError("Image limit must be 1–15.")
    params = {
        "action": "query", "format": "json", "formatversion": "2",
        "generator": "search", "gsrnamespace": "6", "gsrsearch": topic,
        "gsrlimit": str(limit), "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata", "iiurlwidth": "800",
    }
    data = _json_get(API + "?" + urlencode(params))
    images = []
    for page in data.get("query", {}).get("pages", []):
        infos = page.get("imageinfo", [])
        if not infos:
            continue
        info = infos[0]
        meta = info.get("extmetadata") or {}
        field = lambda key: plain((meta.get(key) or {}).get("value", ""))
        name = field("LicenseShortName")
        mime = str(info.get("mime", ""))
        thumb = str(info.get("thumburl", ""))
        title = str(page.get("title", ""))
        page_url = str(info.get("descriptionurl", ""))
        if not title.startswith("File:") or not allowed_license(name) or mime not in MIMES:
            continue
        if urlparse(thumb).scheme != "https" or urlparse(thumb).hostname != "upload.wikimedia.org":
            continue
        if urlparse(page_url).scheme != "https" or urlparse(page_url).hostname != "commons.wikimedia.org":
            continue
        author = field("Artist") or field("Credit") or "Author not specified — inspect Commons page"
        images.append(CommonsImage(
            title=title[:260], file_page=page_url, thumbnail=thumb,
            author=author, license_name=name, license_url=field("LicenseUrl"),
            mime=mime, description=field("ImageDescription"),
        ))
    return images


def add_image(image: CommonsImage, note: str | Path, library: str | Path,
              *, reviewed: bool = False) -> Path:
    """Only write after explicit review. Downloads a limited-size thumbnail.

    Author/license metadata is untrusted and must be checked on the file page.
    """
    if not reviewed:
        raise ValueError("Open the Commons file page and check scientific accuracy and licensing. Use --reviewed to confirm.")
    root = Path(library).expanduser().resolve()
    target = Path(note).expanduser().resolve()
    if not target.is_file() or target.suffix.lower() != ".md" or not target.is_relative_to(root):
        raise ValueError("Choose an existing Markdown note inside the local library.")
    if not allowed_license(image.license_name) or image.mime not in MIMES:
        raise ValueError("Missing accepted image license or unsupported image format.")
    url = urlparse(image.thumbnail)
    if url.scheme != "https" or url.hostname != "upload.wikimedia.org":
        raise ValueError("Only Wikimedia-hosted HTTPS thumbnails can be downloaded.")
    try:
        with urlopen(Request(image.thumbnail, headers={"User-Agent": USER_AGENT}), timeout=20) as response:
            mime = response.headers.get_content_type()
            data = response.read(MAX_IMAGE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise ImageSearchError("Image download failed.") from None
    if len(data) > MAX_IMAGE_BYTES or mime != image.mime:
        raise ImageSearchError("Image too large or unexpected MIME type.")
    # Verify basic signatures and reject executable/text payloads masquerading as images.
    signatures = {
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    if not signatures.get(mime, False):
        raise ImageSearchError("Downloaded file does not match its declared image format.")
    digest = hashlib.sha256(data).hexdigest()[:20]
    directory = target.parent / "external-images"
    directory.mkdir(exist_ok=True)
    dest = directory / (digest + MIMES[mime])
    if not dest.exists():
        dest.write_bytes(data)
    credit = (
        f"\n\n### External educational image: {image.title}\n\n"
        f"![Candidate illustration — verify medical labels](external-images/{dest.name})\n\n"
        f"*Author/credit:* {image.author} · *License:* {image.license_name}"
        + (f" ({image.license_url})" if image.license_url else "")
        + f" · *Source:* {image.file_page} · *Retrieved:* {date.today().isoformat()}\n\n"
        "**Review notice:** Figure selected by the learner; anatomical accuracy not independently verified.\n"
    )
    with target.open("a", encoding="utf-8") as f:
        f.write(credit)
    return dest
