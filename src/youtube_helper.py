"""YouTube SEO — generate optimized descriptions, hashtags, and timestamps.

Generates a full YouTube upload package:
- SEO-optimized description with engagement hooks
- Relevant hashtags (max 15)
- Chapter timestamps from section markers
- Reel cut timestamps (best 60s segments for Shorts/Reels/TikTok)
"""

import json
from src.gemini_helper import generate_text


def generate_youtube_description(script: dict, duration: float) -> str:
    """Generate SEO-optimized YouTube description with engagement hooks."""
    title = script["title"]
    tags = script.get("tags", [])
    description_hint = script.get("description", "")

    prompt = f"""Write a YouTube video description for a CuriousAsian video.

TITLE: "{title}"
TOPIC HINT: "{description_hint}"
TAGS: {', '.join(tags)}
DURATION: {duration:.0f} seconds ({duration/60:.1f} minutes)

RULES:
1. First line: An attention-grabbing hook question or statement (this shows in search results)
2. 2-3 short paragraphs: What the viewer will learn, with curiosity gaps
3. Engagement question: Ask a specific question to drive comments
4. Call to action: Subscribe + like + share
5. Credit line: "Produced by CuriousAsian — Your grandma's rules, finally explained."
6. Keep it under 300 words total
7. Do NOT include hashtags (those go separately)
8. Do NOT include timestamps (those go separately)
9. Use line breaks for readability
10. Write in an engaging, conversational tone — NOT formal/corporate

Return ONLY the description text, no quotes or formatting."""

    result = generate_text(prompt)
    if result:
        return result.strip()

    # Fallback: simple description
    return (
        f"{description_hint}\n\n"
        f"Ever wondered why? This video breaks it all down.\n\n"
        f"Drop a comment: What cultural tradition surprised YOU the most?\n\n"
        f"SUBSCRIBE for daily videos about the fascinating traditions behind everyday habits.\n\n"
        f"Produced by CuriousAsian — Your grandma's rules, finally explained."
    )


def generate_hashtags(script: dict) -> list[str]:
    """Generate relevant YouTube hashtags (max 15)."""
    title = script["title"]
    tags = script.get("tags", [])

    # Always include these
    base_tags = ["#CuriousAsian", "#Culture", "#Explained"]

    # Convert script tags to hashtags
    tag_hashtags = [f"#{tag.replace(' ', '')}" for tag in tags
                    if tag.lower() != "curiousasian"]

    # Generate additional via Gemini
    prompt = f"""Generate 8 relevant YouTube hashtags for this video:
Title: "{title}"
Tags: {', '.join(tags)}

RULES:
- Each hashtag starts with #
- No spaces in hashtags (use CamelCase)
- Mix broad appeal (#Culture) with specific (#JapaneseTipping)
- Include trending/searchable terms
- NO duplicate of: {', '.join(base_tags + tag_hashtags)}
- Return ONLY hashtags, one per line, no numbering"""

    extra = []
    try:
        result = generate_text(prompt)
        if result:
            for line in result.strip().split("\n"):
                line = line.strip()
                if line.startswith("#") and len(line) > 2:
                    extra.append(line)
    except Exception:
        pass

    all_hashtags = base_tags + tag_hashtags + extra
    # Deduplicate (case-insensitive)
    seen = set()
    unique = []
    for h in all_hashtags:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            unique.append(h)

    return unique[:15]


def generate_chapter_timestamps(audio_segments: list[dict]) -> list[dict]:
    """Generate YouTube chapter timestamps from audio segments."""
    chapters = []
    cumulative = 1.5  # after intro bumper

    # Group sections into chapters by type
    current_chapter = None
    chapter_start = cumulative

    section_labels = {
        "hook": "The Hook",
        "build": "The Story",
        "twist": "Plot Twist",
        "payoff": "The Truth",
        "close": "Closing",
    }

    for seg in audio_segments:
        section_type = seg["section_id"].split("_")[0]

        if section_type != current_chapter:
            if current_chapter is not None:
                chapters.append({
                    "time": chapter_start,
                    "label": section_labels.get(current_chapter, current_chapter.title()),
                })
            current_chapter = section_type
            chapter_start = cumulative

        cumulative += seg["duration"]

    # Add last chapter
    if current_chapter is not None:
        chapters.append({
            "time": chapter_start,
            "label": section_labels.get(current_chapter, current_chapter.title()),
        })

    return chapters


def format_timestamp(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins >= 60:
        hours = mins // 60
        mins = mins % 60
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def find_reel_cuts(audio_segments: list[dict], max_reels: int = 3) -> list[dict]:
    """Find the best 60-second segments for Reels/Shorts/TikTok.

    Prioritizes twist and hook sections for maximum engagement.
    """
    reels = []
    cumulative = 1.5  # after intro

    # Score each section by engagement potential
    scored_sections = []
    for seg in audio_segments:
        section_type = seg["section_id"].split("_")[0]
        score = {
            "hook": 5, "twist": 5,
            "payoff": 4, "build": 2, "close": 1,
        }.get(section_type, 2)
        scored_sections.append({
            "start": cumulative,
            "duration": seg["duration"],
            "score": score,
            "section_id": seg["section_id"],
        })
        cumulative += seg["duration"]

    # Find best 60s windows
    total_dur = cumulative
    if total_dur < 70:
        return []  # Video too short for reel cuts

    # Sliding window: find 60s chunks with highest total score
    window_size = 60.0
    best_windows = []

    for i, sec in enumerate(scored_sections):
        window_start = sec["start"]
        window_end = window_start + window_size
        if window_end > total_dur:
            break

        # Sum scores of all sections in this window
        window_score = 0
        sections_in_window = []
        for s in scored_sections:
            if s["start"] >= window_start and s["start"] < window_end:
                window_score += s["score"]
                sections_in_window.append(s["section_id"])

        best_windows.append({
            "start": window_start,
            "end": window_end,
            "score": window_score,
            "sections": sections_in_window,
        })

    # Sort by score, take top N non-overlapping
    best_windows.sort(key=lambda x: x["score"], reverse=True)
    selected = []
    for w in best_windows:
        if len(selected) >= max_reels:
            break
        # Check overlap with already selected
        overlaps = False
        for s in selected:
            if not (w["end"] <= s["start"] or w["start"] >= s["end"]):
                overlaps = True
                break
        if not overlaps:
            selected.append(w)

    # Sort by time order
    selected.sort(key=lambda x: x["start"])
    return selected


def generate_youtube_package(script: dict, audio_segments: list[dict],
                              duration: float) -> dict:
    """Generate complete YouTube upload package.

    Returns dict with: description, hashtags, chapters, reel_cuts, full_description.
    """
    print("\n📋 Generating YouTube package...")

    description = generate_youtube_description(script, duration)
    hashtags = generate_hashtags(script)
    chapters = generate_chapter_timestamps(audio_segments)
    reel_cuts = find_reel_cuts(audio_segments)

    # Build full description with chapters and hashtags
    parts = [description, ""]

    # Chapters
    if chapters:
        parts.append("CHAPTERS:")
        for ch in chapters:
            parts.append(f"{format_timestamp(ch['time'])} {ch['label']}")
        parts.append("")

    # Hashtags
    if hashtags:
        parts.append(" ".join(hashtags))

    full_description = "\n".join(parts)

    package = {
        "title": script["title"],
        "description": description,
        "full_description": full_description,
        "hashtags": hashtags,
        "chapters": chapters,
        "reel_cuts": [
            {
                "start": format_timestamp(r["start"]),
                "end": format_timestamp(r["end"]),
                "start_seconds": round(r["start"], 1),
                "end_seconds": round(r["end"], 1),
                "sections": r["sections"],
            }
            for r in reel_cuts
        ],
        "tags": script.get("tags", []),
    }

    print(f"  📝 Description: {len(description)} chars")
    print(f"  #️⃣  Hashtags: {len(hashtags)}")
    print(f"  📑 Chapters: {len(chapters)}")
    print(f"  🎬 Reel cuts: {len(reel_cuts)}")

    return package
