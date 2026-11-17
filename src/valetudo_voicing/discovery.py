"""Multi-source character voice discovery (YouTube via yt-dlp + 101soundboards)."""

from dataclasses import dataclass, field
import re
from urllib.parse import quote_plus
import httpx

EXCLUDED_TITLE_KEYWORDS = {
    "ai cover",
    "ai voice",
    "cover",
    "remix",
    "karaoke",
    "reaction",
    "reacts",
    "type beat",
    "speedpaint",
    "parody",
    "parodie",
    "ytaudio",
    "music video",
    "official audio",
    "instrumental",
}

POSITIVE_TITLE_KEYWORDS = {
    "fr": ["vf", "voix", "répliques", "repliques", "citations", "français", "francais", "doublage"],
    "en": ["voice", "voice lines", "voicelines", "quotes", "dialogue", "lines", "clips"],
    "es": ["voz", "frases", "doblaje", "español"],
    "de": ["stimme", "zitate", "sprüche", "deutsch"],
    "it": ["voce", "frasi", "doppiaggio", "italiano"],
    "ja": ["ボイス", "セリフ", "声", "voice"],
}


@dataclass
class VoiceCandidate:
    """A candidate voice source discovered for a character."""

    source: str  # "youtube" or "101soundboards"
    title: str
    url: str
    duration_sec: float | None = None
    channel: str = ""
    score: float = 0.0
    audio_urls: list[str] = field(default_factory=list)


def _build_youtube_queries(character: str, lang: str) -> list[str]:
    lang_code = lang.lower().split("-")[0]
    if lang_code == "fr":
        return [
            f"{character} voix vf répliques",
            f"{character} voice lines fr",
        ]
    if lang_code == "en":
        return [
            f"{character} voice lines",
            f"{character} quotes dialogue",
        ]
    return [
        f"{character} voice {lang_code}",
        f"{character} {lang_code} dialogue",
    ]


def _score_youtube_entry(title: str, duration: float | None, character: str, lang: str) -> float | None:
    """Return a relevance score, or None if the entry should be filtered out."""
    lower_title = title.lower()
    for bad in EXCLUDED_TITLE_KEYWORDS:
        if bad in lower_title:
            return None

    if duration is not None and (duration < 6 or duration > 1200):
        return None

    score = 0.0
    char_tokens = [t for t in re.split(r"\s+", character.lower()) if len(t) > 1]
    if char_tokens:
        matched = sum(1 for t in char_tokens if t in lower_title)
        score += 3.0 * (matched / len(char_tokens))

    lang_code = lang.lower().split("-")[0]
    for kw in POSITIVE_TITLE_KEYWORDS.get(lang_code, []):
        if kw in lower_title:
            score += 1.5

    if duration is not None:
        if 15 <= duration <= 180:
            score += 2.0
        elif 180 < duration <= 600:
            score += 1.0

    return score


def search_youtube_candidates(character: str, lang: str = "fr", limit: int = 5) -> list[VoiceCandidate]:
    """Search YouTube via yt-dlp without requiring an API key."""
    import yt_dlp  # type: ignore

    queries = _build_youtube_queries(character, lang)
    seen_urls: set[str] = set()
    candidates: list[VoiceCandidate] = []

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for query in queries:
            try:
                info = ydl.extract_info(f"ytsearch8:{query}", download=False)
            except Exception:
                continue

            for entry in (info or {}).get("entries", []) or []:
                url = entry.get("url") or entry.get("webpage_url")
                if not url:
                    vid_id = entry.get("id")
                    if vid_id:
                        url = f"https://www.youtube.com/watch?v={vid_id}"
                if not url or url in seen_urls:
                    continue
                if url and not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={url}"

                title = entry.get("title") or ""
                duration = entry.get("duration")
                dur_float = float(duration) if duration is not None else None

                score = _score_youtube_entry(title, dur_float, character, lang)
                if score is None:
                    continue

                seen_urls.add(url)
                candidates.append(
                    VoiceCandidate(
                        source="youtube",
                        title=title,
                        url=url,
                        duration_sec=dur_float,
                        channel=entry.get("channel") or entry.get("uploader") or "",
                        score=score,
                    )
                )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:limit]


def search_soundboard_candidates(character: str, limit: int = 2) -> list[VoiceCandidate]:
    """Search 101soundboards.com for public character soundboards (best-effort, graceful fallback)."""
    search_url = f"https://www.101soundboards.com/search/{quote_plus(character)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }
    candidates: list[VoiceCandidate] = []

    try:
        with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(search_url)
            if resp.status_code != 200:
                return []
            html = resp.text
            # Match board links like /boards/12345-character-name
            board_matches = re.findall(r'href="(/boards/\d+-[^"]+)"[^>]*>([^<]+)<', html)
            seen: set[str] = set()
            for rel_path, raw_title in board_matches:
                board_url = f"https://www.101soundboards.com{rel_path}"
                if board_url in seen:
                    continue
                seen.add(board_url)
                title = re.sub(r"\s+", " ", raw_title).strip()

                # Fetch board page to extract direct mp3/wav sound URLs
                board_resp = client.get(board_url)
                if board_resp.status_code != 200:
                    continue
                mp3_urls = re.findall(r'https?://[^"\'\s<>]+\.(?:mp3|wav)', board_resp.text)
                # Deduplicate while preserving order
                unique_clips = list(dict.fromkeys(mp3_urls))[:8]
                if not unique_clips:
                    continue

                candidates.append(
                    VoiceCandidate(
                        source="101soundboards",
                        title=f"{title} ({len(unique_clips)} extraits)",
                        url=board_url,
                        duration_sec=None,
                        channel="101soundboards",
                        score=3.5,
                        audio_urls=unique_clips,
                    )
                )
                if len(candidates) >= limit:
                    break
    except Exception:
        return []

    return candidates


def search_character_voices(character: str, lang: str = "fr", limit: int = 5) -> list[VoiceCandidate]:
    """Search across YouTube and public soundboards and return ranked candidates."""
    yt_candidates = search_youtube_candidates(character, lang=lang, limit=limit)
    sb_candidates = search_soundboard_candidates(character, limit=2)

    combined = yt_candidates + sb_candidates
    combined.sort(key=lambda c: c.score, reverse=True)
    return combined[:limit]
