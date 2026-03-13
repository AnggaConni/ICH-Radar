# 🌏 ICH Radar — Global Intangible Cultural Heritage Intelligence Engine

ICH Radar is an automated cultural intelligence system designed to discover, analyze, and document Intangible Cultural Heritage (ICH) practices worldwide.

Powered by Google Gemini with Google Search Grounding, the engine autonomously scans blogs, local news, community websites, and other open online sources to identify traditional knowledge, rituals, crafts, cuisine, and social practices that may not yet be formally documented.

By transforming unstructured information into structured cultural-heritage records, ICH Radar helps map living traditions, identify potential shared heritage across regions, and support early safeguarding efforts before cultural practices disappear.

---

## 🏗️ Architecture

Unlike traditional web scrapers that rely on direct crawling and often get blocked, ICH Radar delegates the discovery process to Google's infrastructure through AI Search Grounding. This approach allows the system to access information across diverse online sources — including blogs, regional news, and community archives — even when conventional scrapers fail.

The AI then converts these discoveries into structured heritage records, including descriptions, cultural significance, geographic location, and traditional processes or practices.

```
GitHub Actions (Scheduled Automation)
        │
        ▼
   scraper.py (AI Discovery Engine)
        │
        ├──► Gemini AI + Google Search Grounding
        │      ├── Discovers cultural practices via multilingual keywords
        │      ├── Extracts structured heritage data
        │      └── Detects shared heritage relationships across regions
        │
        ├──► Microlink.io API
        │      └── Generates screenshot thumbnails from source pages
        │
        ▼
  data.json (ICH Inventory Database)
        │
        ▼
 Git Commit & Push
        │
        ▼
 GitHub Pages → Interactive Cultural Heritage Map & Dashboard

```

---

## Output: `data.json`

```json
{
  "summary": {
    "generated_at": "2026-03-13T02:43:12Z",
    "total_ich_elements": 248,
    "complete_records": 180,
    "incomplete_records": 68,
    "categories_breakdown": {
      "Culinary Traditions": 65,
      "Traditional Craftsmanship": 54,
      "Performing Arts": 42,
      "Oral Traditions": 36,
      "Social Practices & Rituals": 51
    }
  },
  "inventory": [
    {
      "id": "ich-4b1f9c3a",
      "element_name": "Traditional Bamboo Fish Trap Weaving",
      "category": "Traditional Craftsmanship",
      "location": {
        "country": "Indonesia",
        "provinces": ["West Java"]
      },
      "resume_analisa": {
        "description": "A traditional fishing trap weaving technique using bamboo strips practiced by rural fishing communities.",
        "cultural_significance": "Represents local ecological knowledge and sustainable fishing practices passed through generations."
      },
      "resume_tata_cara": {
        "type": "crafting_process",
        "materials_and_tools": ["Bamboo", "Knife", "Binding fiber"],
        "step_by_step": [
          "Split bamboo into thin strips",
          "Weave circular base frame",
          "Construct funnel entrance",
          "Secure trap with binding fiber"
        ]
      },
      "shared_heritage_detection": {
        "is_shared": true,
        "confidence_score": 0.84,
        "related_elements": [
          {
            "country": "Vietnam",
            "element_name": "Traditional Bamboo Fish Trap",
            "relationship_reason": "Similar weaving structure used in river fishing communities."
          }
        ]
      },
      "completion_status": "COMPLETE"
    }
  ]
}
```

---

## Setup

### 1. Add your Gemini API key
In your GitHub repository → **Settings → Secrets and variables → Actions**:

| Secret name    | Value                   |
|----------------|-------------------------|
| `GEMINI_API_KEY` | Your Google Gemini key |

Get a free key at [aistudio.google.com](https://aistudio.google.com).

### 2. Place files
```
your-repo/
├── .github/workflows/
│   └── crawler.yml         # GitHub Actions workflow
├── scraper.py              # Main Python intelligence engine
├── index.html              # The Dashboard UI
├── data.json               # Auto-generated results (committed by bot)
└── history.json            # Crawl state tracker (committed by bot)
```

### 3. Run manually

Run Manually (Bypass 2-Day Guard)

Go to Actions → ICH Radar Auto-Crawler → Run workflow.

Set Force crawl now to true if you want to bypass the 2-day waiting period and scan immediately.

---

## Schedule

The crawler runs on an interval of 2 days.

A built-in 2-day guard in `scraper.py` also prevents redundant re-runs if the workflow is triggered too soon (e.g., after a `git push`).

To change the interval, edit `CRAWL_INTERVAL_DAYS` in `scraper.py`.


---

## Adding more keywords

Edit `ARTIFACT_KEYWORDS` in `scraper.py`:

```python
KEYWORDS = [
# Add your targeted search patterns here:
# ─────────────────────────────────────────────
# UNREGISTERED / LOCAL FOLKLORE / COMMUNITY PRACTICES
# (Keywords targeting blogs, social media, local news, non-UNESCO)
# ─────────────────────────────────────────────

"unregistered local heritage traditions",
"endangered local folklore practices",
"everyday community cultural practices",
"forgotten village traditions",
"ancestral customs still practiced today",
"oral traditions passed down generations",
"traditional knowledge from elders",
"community rituals preserved by villagers",
"local craft traditions handmade methods",
"ancient village ceremonies still practiced",
"traditional farming knowledge ancestors",
"indigenous healing rituals traditional medicine",
"traditional food preparation ancestral recipe",

"tradisi lokal masyarakat adat kampung",
"kebiasaan turun temurun warga",
"resep rahasia leluhur masakan daerah",
"ritual adat lokal yang hampir punah",
"cerita rakyat dan mitos lokal",
"upacara adat desa yang jarang diketahui",
"pengetahuan tradisional masyarakat adat",
"kerajinan tangan tradisional desa",
"cara memasak tradisional warisan nenek moyang",
"ritual panen tradisional masyarakat lokal",

"prácticas culturales comunitarias no registradas",
"tradiciones de pueblos originarios blog",
"rituales tradicionales de comunidades indígenas",
"recetas ancestrales tradicionales de pueblo",
"costumbres heredadas de generaciones",

```

## Purpose

ICH Radar aims to support:

• cultural heritage research
• early detection of endangered traditions
• mapping of shared cultural heritage across regions
• digital documentation of community knowledge

The system focuses particularly on locally practised traditions that may not yet appear in official heritage inventories, helping researchers and institutions identify cultural practices before they disappear.

## ⚖️ Disclaimer

This tool is intended for cultural-heritage research, documentation, and safeguarding support purposes. It aligns with the principles of the UNESCO Convention for the Safeguarding of the Intangible Cultural Heritage adopted in 2003.

License: MIT
