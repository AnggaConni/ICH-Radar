"""
=======================================================================
  ICH SHARED HERITAGE RADAR v6.3 — Global Intelligence Engine
  AI Engine : Gemini 2.5 Flash (data pipeline) + Gemini 3.5 Flash-Lite (resource intelligence)
  Mode      : Alternating daily pipeline (Discovery/Data -> Resource & Opportunity)
  Feature   : Quality over Quantity (Iterative Looping), Anti-Redundancy, Wikimedia Fallback
=======================================================================
"""

import os
import json
import hashlib
import logging
import random
import re
import time
from datetime import datetime
import requests

# ── Logging Configuration ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("ICH_Radar")

# ── File Paths ──
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
DATA_FILE    = os.path.join(BASE_DIR, "data.json")
RESUME_FILE  = os.path.join(BASE_DIR, "resume.json")

# ======================================================================
# GLOBAL KEYWORD DATABASE FOR DISCOVERY (Multi-Language)
# ======================================================================
from keyword_database import KEYWORDS

# ======================================================================
# DATA PERSISTENCE & MIGRATION
# ======================================================================

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "listings" in data:
                    log.info("Migrating old database schema to ICH format...")
                    return {"summary": {}, "inventory": []}
                if "inventory" not in data:
                    data["inventory"] = []
                return data
        except Exception as e:
            log.warning(f"Database corrupted, starting fresh: {e}")
            
    return {"summary": {}, "inventory": []}

def save_db(db):
    db["summary"] = calculate_summary(db["inventory"])
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def calculate_summary(inventory):
    complete = len([x for x in inventory if x.get("completion_status") == "COMPLETE"])
    incomplete = len(inventory) - complete
    
    categories = {}
    for item in inventory:
        item_categories = item.get("categories") or [item.get("category", "Unknown")]
        for cat in item_categories:
            categories[cat] = categories.get(cat, 0) + 1
        
    return {
        "generated_at": datetime.now().isoformat() + "Z",
        "total_ich_elements": len(inventory),
        "complete_records": complete,
        "incomplete_records": incomplete,
        "categories_breakdown": categories
    }

def get_wikimedia_image(query):
    """
    Fallback function: Fetches a thumbnail from Wikimedia Commons based on the query.
    """
    try:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "prop": "pageimages",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": 1,
            "pithumbsize": 800
        }
        
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if "query" in data and "pages" in data["query"]:
            pages = data["query"]["pages"]
            first_page = list(pages.values())[0]
            if "thumbnail" in first_page:
                log.info(f"Wikimedia fallback success for query: '{query}'")
                return first_page["thumbnail"]["source"]
    except Exception as e:
        log.warning(f"Wikimedia fallback failed for '{query}': {e}")
        
    return None

def get_screenshot_url(url, element_name="Unknown Element"):
    """
    Tries to get a screenshot from Microlink. 
    If the URL is missing or invalid, it falls back to Wikimedia Commons.
    If the URL is ALREADY an image (e.g., .jpg), it returns the URL directly.
    """
    if not url or url.lower() == "n/a" or url.startswith("http://n/a"):
        log.info(f"Invalid URL for '{element_name}', triggering Wikimedia fallback...")
        wiki_img = get_wikimedia_image(element_name)
        return wiki_img if wiki_img else "N/A"
        
    # SMART CHECK: If it's already an image file, DO NOT use Microlink screenshot API.
    lower_url = url.lower()
    if lower_url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
        log.info(f"Direct image URL detected for '{element_name}'. Skipping Microlink API.")
        return url
        
    encoded_url = requests.utils.quote(url)
    return f"https://api.microlink.io/?url={encoded_url}&screenshot=true&meta=false&embed=screenshot.url"

def generate_id(name):
    return "ich-" + hashlib.md5(name.lower().encode()).hexdigest()[:8]

def get_coordinates(location_name):
    """
    Mengambil latitude & longitude dari Nominatim API.
    Sama seperti versi JS, kita membersihkan nama jika ada tanda kurung.
    """
    if not location_name or location_name == "N/A":
        return None, None

    try:
        # Bersihkan nama (Contoh: "Canada (Quebec)" -> "Canada")
        clean_name = location_name.split('(')[0].strip()
        
        # Nominatim butuh User-Agent agar tidak diblokir
        headers = {'User-Agent': 'ICH-Shared-Heritage-Radar-Crawler'}
        url = f"https://nominatim.openstreetmap.org/search?format=json&q={requests.utils.quote(clean_name)}&limit=1"
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if data and len(data) > 0:
            log.info(f"Geocoding Success: {clean_name} -> [{data[0]['lat']}, {data[0]['lon']}]")
            return float(data[0]['lat']), float(data[0]['lon'])
            
    except Exception as e:
        log.warning(f"Geocoding Failed for {location_name}: {e}")
    
    return None, None

# ======================================================================
# DATA AUDIT (Check for missing thumbnails)
# ======================================================================

def audit_inventory(inventory):
    """Scans inventory and marks items with missing images as INCOMPLETE."""
    audited_count = 0
    for item in inventory:
        thumb = item.get("thumbnail_url", "")
        # Jika gambar kosong, N/A, atau rusak, paksa turunkan statusnya
        if not thumb or thumb == "N/A" or "placeholder" in thumb.lower():
            if item.get("completion_status") == "COMPLETE":
                item["completion_status"] = "INCOMPLETE"
                log.info(f"Audit: Marked '{item.get('element_name')}' as INCOMPLETE due to missing thumbnail.")
                audited_count += 1
    return audited_count

# ======================================================================
# CONTROLLED VOCABULARY & NORMALIZATION
# ======================================================================

VALID_HERITAGE_CATEGORIES = [
    "Culinary Traditions",
    "Traditional Craftsmanship",
    "Performing Arts",
    "Oral Traditions",
    "Social Practices & Rituals",
]

VALID_DRR_CATEGORIES = [
    "Not Directly Related to DRR",
    "Indigenous Knowledge & Early Warning",
    "Ecosystem-Based Disaster Risk Reduction",
    "Resilient Livelihoods & Food Security",
    "Resilient Housing & Settlement Practices",
    "Traditional Emergency Preparedness",
    "Social Cohesion & Mutual Aid",
    "Climate Adaptation & Resilience",
    "Traditional Healing & Health Resilience",
    "Other Disaster Resilience Practice",
]

VALID_DRR_RELEVANCE = [
    "Directly Related to DRR",
    "Indirectly Related to DRR",
    "Not Directly Related to DRR",
]

# Hazard vocabulary kept aligned with drr.html's current visual taxonomy.
VALID_HAZARD_CATEGORIES = [
    "Tsunami",
    "Earthquake",
    "Drought",
    "Flood",
    "Typhoon",
    "Wildfire",
]


def normalize_categories(value):
    """Normalize one or more ICH thematic categories into a canonical list."""
    if isinstance(value, list):
        values = value
    elif value:
        values = [value]
    else:
        values = []

    aliases = {
        "culinary": "Culinary Traditions",
        "culinary tradition": "Culinary Traditions",
        "culinary traditions": "Culinary Traditions",
        "traditional cuisine": "Culinary Traditions",
        "food heritage": "Culinary Traditions",
        "food traditions": "Culinary Traditions",
        "gastronomy": "Culinary Traditions",
        "traditional food": "Culinary Traditions",
        "traditional craft": "Traditional Craftsmanship",
        "traditional craftsmanship": "Traditional Craftsmanship",
        "craft": "Traditional Craftsmanship",
        "craftsmanship": "Traditional Craftsmanship",
        "handicraft": "Traditional Craftsmanship",
        "performing art": "Performing Arts",
        "performing arts": "Performing Arts",
        "oral tradition": "Oral Traditions",
        "oral traditions": "Oral Traditions",
        "social practice": "Social Practices & Rituals",
        "social practices": "Social Practices & Rituals",
        "social practices & rituals": "Social Practices & Rituals",
        "ritual": "Social Practices & Rituals",
        "rituals": "Social Practices & Rituals",
    }

    result = []
    for value in values:
        raw = str(value or "").strip().lower()
        canonical = aliases.get(raw)

        if not canonical:
            for key, mapped in aliases.items():
                if key in raw:
                    canonical = mapped
                    break

        if canonical and canonical not in result:
            result.append(canonical)

    return [x for x in result if x in VALID_HERITAGE_CATEGORIES]


def normalize_category(value):
    """Backward-compatible helper: return the first canonical ICH category."""
    categories = normalize_categories(value)
    return categories[0] if categories else None


def normalize_drr_category(value):
    raw = str(value or "").strip().lower()
    aliases = {
        "none": "Not Directly Related to DRR",
        "not related": "Not Directly Related to DRR",
        "not directly related": "Not Directly Related to DRR",
        "early warning": "Indigenous Knowledge & Early Warning",
        "indigenous knowledge": "Indigenous Knowledge & Early Warning",
        "indigenous early warning": "Indigenous Knowledge & Early Warning",
        "ecosystem based drr": "Ecosystem-Based Disaster Risk Reduction",
        "ecosystem-based drr": "Ecosystem-Based Disaster Risk Reduction",
        "nature based drr": "Ecosystem-Based Disaster Risk Reduction",
        "food security": "Resilient Livelihoods & Food Security",
        "livelihood resilience": "Resilient Livelihoods & Food Security",
        "resilient livelihoods": "Resilient Livelihoods & Food Security",
        "resilient housing": "Resilient Housing & Settlement Practices",
        "settlement resilience": "Resilient Housing & Settlement Practices",
        "emergency preparedness": "Traditional Emergency Preparedness",
        "preparedness": "Traditional Emergency Preparedness",
        "social cohesion": "Social Cohesion & Mutual Aid",
        "mutual aid": "Social Cohesion & Mutual Aid",
        "climate adaptation": "Climate Adaptation & Resilience",
        "climate resilience": "Climate Adaptation & Resilience",
        "health resilience": "Traditional Healing & Health Resilience",
        "traditional healing": "Traditional Healing & Health Resilience",
    }
    if raw in aliases:
        return aliases[raw]
    for key, canonical in aliases.items():
        if key in raw:
            return canonical
    return None


def normalize_drr_relevance(value):
    raw = str(value or "").strip().lower()
    aliases = {
        "direct": "Directly Related to DRR",
        "directly related": "Directly Related to DRR",
        "directly related to drr": "Directly Related to DRR",
        "indirect": "Indirectly Related to DRR",
        "indirectly related": "Indirectly Related to DRR",
        "indirectly related to drr": "Indirectly Related to DRR",
        "none": "Not Directly Related to DRR",
        "not related": "Not Directly Related to DRR",
        "not directly related": "Not Directly Related to DRR",
        "not directly related to drr": "Not Directly Related to DRR",
    }
    if raw in aliases:
        return aliases[raw]
    for key, canonical in aliases.items():
        if key in raw:
            return canonical
    return None


def normalize_hazard_categories(values):
    """Normalize Gemini hazard labels into the six hazard categories used by drr.html."""
    if not isinstance(values, list):
        return []

    aliases = {
        "tsunami": "Tsunami",
        "marine surge": "Tsunami",
        "storm surge": "Tsunami",
        "earthquake": "Earthquake",
        "seismic": "Earthquake",
        "ground shaking": "Earthquake",
        "drought": "Drought",
        "heatwave": "Drought",
        "heat wave": "Drought",
        "flood": "Flood",
        "flooding": "Flood",
        "landslide": "Flood",
        "typhoon": "Typhoon",
        "cyclone": "Typhoon",
        "gale": "Typhoon",
        "wildfire": "Wildfire",
        "bushfire": "Wildfire",
        "forest fire": "Wildfire",
    }

    result = []
    for value in values:
        raw = str(value or "").strip().lower()
        canonical = aliases.get(raw)

        if not canonical:
            for key, mapped in aliases.items():
                if key in raw:
                    canonical = mapped
                    break

        if canonical and canonical not in result:
            result.append(canonical)

    return result


def normalize_ai_classification(item):
    """Enforce a multi-category ICH schema plus structured DRR relevance."""
    raw_categories = item.get("categories")
    if raw_categories is None:
        raw_categories = item.get("category")

    categories = normalize_categories(raw_categories)
    item["categories"] = categories
    item["categories_valid"] = len(categories) > 0

    # Backward compatibility for radar.html: keep the first category as
    # the legacy scalar category. New UI code should prefer categories.
    item["category"] = categories[0] if categories else "Unclassified"
    item["category_valid"] = len(categories) > 0

    analysis = item.setdefault("resume_analisa", {})

    drr_category = normalize_drr_category(analysis.get("drr_category"))
    drr_valid = drr_category is not None
    analysis["drr_category_valid"] = drr_valid
    analysis["drr_category"] = drr_category or "Not Directly Related to DRR"

    drr_relevance = normalize_drr_relevance(analysis.get("drr_relevance_level"))
    if drr_relevance is None:
        drr_relevance = (
            "Directly Related to DRR"
            if analysis["drr_category"] != "Not Directly Related to DRR" and drr_valid
            else "Not Directly Related to DRR"
        )
    analysis["drr_relevance_level"] = drr_relevance

    hazards = normalize_hazard_categories(analysis.get("hazard_categories", []))
    analysis["hazard_categories"] = hazards

    # Compatibility field for current drr.html.
    # It is derived from the structured DRR classification, not AI-generated.
    analysis["drr_relevance"] = (
        analysis["drr_category"] != "Not Directly Related to DRR"
        and drr_valid
    )

    return item

# ======================================================================
# CORE: GEMINI AI INTERACTION
# ======================================================================

class GeminiQuotaExhausted(RuntimeError):
    """Project quota/billing allowance is exhausted; stop this run cleanly."""


def call_gemini(api_key, prompt, model="gemini-2.5-flash", max_output_tokens=8192):
    """Call Gemini with Google Search grounding and resilient transient-error handling."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    # Gemini 3.x uses the current google_search tool name.
    # Gemini 2.5 keeps the legacy camelCase tool name already used by this repo.
    search_tool = {"google_search": {}} if model.startswith("gemini-3") else {"googleSearch": {}}

    generation_config = {
        "maxOutputTokens": max_output_tokens
    }

    # Gemini 3.x no longer needs the old sampling controls used by 2.5.
    if not model.startswith("gemini-3"):
        generation_config["temperature"] = 0.2

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [search_tool],
        "generationConfig": generation_config
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    transient_statuses = {408, 429, 500, 502, 503, 504}
    max_attempts = 4

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=180)

            if response.status_code == 200:
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    pass

                # Robust fallback: decode the first complete JSON object/array.
                decoder = json.JSONDecoder()
                candidates = []
                for idx, char in enumerate(text):
                    if char not in "[{":
                        continue
                    try:
                        obj, end_idx = decoder.raw_decode(text[idx:])
                        trailing = text[idx + end_idx:].strip()
                        if not trailing:
                            return obj
                        candidates.append(obj)
                    except json.JSONDecodeError:
                        continue

                if candidates:
                    return candidates[0]

                raise json.JSONDecodeError(
                    "No valid standalone JSON document found", text, 0
                )

            if response.status_code in transient_statuses:
                error_text = response.text[:2000]
                error_status = ""
                error_code = ""
                error_message = ""
                try:
                    error_payload = response.json().get("error", {})
                    error_status = str(error_payload.get("status", ""))
                    error_code = str(error_payload.get("code", ""))
                    error_message = str(error_payload.get("message", ""))
                except (ValueError, AttributeError):
                    pass

                hard_quota = (
                    response.status_code == 429
                    and (
                        "exceeded your current quota" in error_message.lower()
                        or error_code.lower() == "quota_exceeded"
                        or error_status.upper() == "QUOTA_EXCEEDED"
                    )
                )
                if hard_quota:
                    log.error(
                        "Gemini project quota exhausted for %s. Stopping retries for this run: %s",
                        model,
                        error_message or error_text
                    )
                    raise GeminiQuotaExhausted(error_message or error_text)

                if attempt < max_attempts:
                    delay = min(30, (2 ** (attempt - 1)) + random.uniform(0.25, 1.25))
                    log.warning(
                        "Gemini transient HTTP %s on attempt %s/%s for %s. "
                        "Retrying in %.1fs...",
                        response.status_code, attempt, max_attempts, model, delay
                    )
                    time.sleep(delay)
                    continue

                log.error(
                    "Gemini transient HTTP %s persisted after %s attempts for %s: %s",
                    response.status_code, max_attempts, model, error_text
                )
                return None

            log.error(
                "Google API Error (%s) for %s: %s",
                response.status_code, model, response.text[:1500]
            )
            return None

        except json.JSONDecodeError as je:
            preview = text[:1200] if "text" in locals() else ""
            log.error(
                "Gemini API failure (JSON Parse Error) for %s: %s. Response preview: %s",
                model, je, preview
            )
            return None

        except requests.RequestException as exc:
            if attempt < max_attempts:
                delay = min(30, (2 ** (attempt - 1)) + random.uniform(0.25, 1.25))
                log.warning(
                    "Gemini network error on attempt %s/%s for %s: %s. Retrying in %.1fs...",
                    attempt, max_attempts, model, exc, delay
                )
                time.sleep(delay)
                continue

            log.error("Gemini network failure after %s attempts for %s: %s", max_attempts, model, exc)
            return None

        except Exception as e:
            log.error("Gemini API failure for %s: %s", model, e)
            return None

    return None

# ======================================================================
# PHASE 1: ENRICHMENT (Fixing Incomplete Data)
# ======================================================================

def enrich_incomplete_items(api_key, inventory):
    incomplete_items = [item for item in inventory if item.get("completion_status") != "COMPLETE"]
    if not incomplete_items:
        log.info("No incomplete items found. Enrichment phase skipped.")
        return 0
    
    log.info(f"Found {len(incomplete_items)} incomplete items. Starting enrichment...")
    enriched_count = 0
    
    for item in incomplete_items[:3]:
        element_name = item.get("element_name")
        current_sources = item.get("source_urls", [])
        
        # Deteksi apakah item ini masuk antrean karena gambarnya hilang
        needs_image = not item.get("thumbnail_url") or item.get("thumbnail_url") == "N/A"
        image_instruction = "Crucially, this record lacks a valid image. You MUST find a new source URL (like a news article, official site, or Wikipedia) that contains a clear, high-quality image of this heritage." if needs_image else ""
        
        log.info(f"Enriching: {element_name}")
        
        prompt = f"""
        You are a Cultural Heritage expert. I have an incomplete record for the Cultural Heritage practice/tradition: "{element_name}".
        Current known sources: {current_sources}.
        
        Please use Google Search to find the missing information (e.g., specific step-by-step crafting process, authentic recipe, or detailed history). 
        You can search through local news, community blogs, and social media.
        Find AT LEAST ONE NEW source URL to add to the existing ones.
        {image_instruction}
        
        IMPORTANT: DO NOT output any links containing 'vertexaisearch.cloud.google.com' or 'grounding-api-redirect'. Output the direct, true website URL.
        Classify the practice's relationship to Disaster Risk Reduction (DRR).
        
        First set "drr_relevance_level" to exactly ONE:
        - Directly Related to DRR
        - Indirectly Related to DRR
        - Not Directly Related to DRR
        
        Use "Directly Related to DRR" only when the documented practice itself has a clear disaster risk reduction, preparedness, adaptation, resilience, recovery-support, or risk-communication function.
        Use "Indirectly Related to DRR" when the practice contributes to resilience through a secondary pathway (for example livelihood continuity or social cohesion) but is not itself a direct risk-reduction measure.
        Use "Not Directly Related to DRR" when no meaningful evidence connects the practice to disaster resilience.
        
        Then choose exactly ONE primary "drr_category" from this controlled vocabulary:
        - Not Directly Related to DRR
        - Indigenous Knowledge & Early Warning
        - Ecosystem-Based Disaster Risk Reduction
        - Resilient Livelihoods & Food Security
        - Resilient Housing & Settlement Practices
        - Traditional Emergency Preparedness
        - Social Cohesion & Mutual Aid
        - Climate Adaptation & Resilience
        - Traditional Healing & Health Resilience
        - Other Disaster Resilience Practice
        
        Set "drr_category_valid" to true ONLY when the selected category is clearly supported by the evidence.
        If there is no meaningful DRR connection, use "Not Directly Related to DRR".
        
        Also classify which disaster hazards the practice directly helps address.
        Use ZERO OR MORE values from exactly this vocabulary:
        - Tsunami
        - Earthquake
        - Drought
        - Flood
        - Typhoon
        - Wildfire
        Do not infer a hazard merely because the practice exists in a disaster-prone area; select hazards only when the documented mechanism supports the connection.
        Explain the evidence-based mechanism in "drr_mechanism".
        
        Respond ONLY with a JSON object representing the UPDATED element.
        Ensure ALL output data values and keys are strictly in ENGLISH.
        For "categories", select ONE OR MORE (maximum 3) of these canonical ICH thematic categories: Culinary Traditions, Traditional Craftsmanship, Performing Arts, Oral Traditions, Social Practices & Rituals.
Use multiple categories when the same living heritage practice genuinely spans more than one domain. Do not add a category merely because it is adjacent or geographically associated.
Set "categories_valid" to true only when at least one selected category is clearly supported by the evidence.
        If you find the missing data, change "completion_status" to "COMPLETE".
        
        Required JSON Structure:
        {{
            "id": "{item.get('id')}",
            "element_name": "{element_name}",
            "categories": ["Culinary Traditions"],
            "categories_valid": true,
            "category": "Culinary Traditions",
            "category_valid": true,
            "thumbnail_url": "{item.get('thumbnail_url')}",
            "source_urls": ["<old_url>", "<new_found_url>"],
            "scraped_at": "{datetime.now().isoformat()}Z",
            "location": {{ 
                        "country": "...", 
                        "provinces": ["..."],
                        "lat": null, 
                        "lng": null 
        }},
            "resume_analisa": {{ 
            "description": "...", 
            "cultural_significance": "...", 
            "drr_category": "Not Directly Related to DRR",
            "drr_category_valid": true,
            "drr_relevance_level": "Not Directly Related to DRR",
            "hazard_categories": [],
            "drr_mechanism": "Brief evidence-based explanation of the disaster resilience mechanism, otherwise null",
            "gemini_tags": ["..."] 
        }},
            "resume_tata_cara": {{ "type": "crafting_process/culinary_recipe/ritual_sequence", "materials_and_tools": ["..."], "step_by_step": ["..."] }},
            "shared_heritage_detection": {{ "is_shared": true, "confidence_score": 0.95, "related_elements": [{{ "country": "...", "element_name": "...", "relationship_reason": "..." }}] }},
            "completion_status": "COMPLETE"
        }}
        """
        
# BARIS DI BAWAH INI SEKARANG SUDAH MASUK KE DALAM LOOP (Indentasi Benar)
        updated_item = call_gemini(api_key, prompt, model="gemini-2.5-flash")
        if updated_item and isinstance(updated_item, dict):
            normalize_ai_classification(updated_item)
            resource_schema_defaults(updated_item)
            # --- LOGIKA KOORDINAT ---
            country = updated_item.get("location", {}).get("country", "")
            lat, lng = get_coordinates(country)
            
            # Perbaikan: Inisialisasi key "location" untuk mencegah KeyError
            updated_item.setdefault("location", {})
            updated_item["location"]["lat"] = lat
            updated_item["location"]["lng"] = lng
            
            index = inventory.index(item)
            inventory[index] = updated_item
            enriched_count += 1
            log.info(f"Successfully enriched {element_name} (Coords: {lat}, {lng})")
        
        time.sleep(5) 
        
    return enriched_count


# ======================================================================
# RESOURCE & OPPORTUNITY ENRICHMENT
# Runs on alternating days against existing inventory records.
# ======================================================================

from resource_intelligence import (
    resource_schema_defaults,
    resource_enrichment_score,
    enrich_resource_data as _enrich_resource_data,
)


def enrich_resource_data(api_key, inventory):
    """Bind resource intelligence to the shared Gemini client and logger."""
    return _enrich_resource_data(
        api_key,
        inventory,
        call_gemini=call_gemini,
        quota_exception=GeminiQuotaExhausted,
        logger=log,
        max_items=os.environ.get("RESOURCE_ENRICH_LIMIT", "2"),
    )


# ======================================================================
# PHASE 2: DISCOVERY (Finding New Data)
# ======================================================================


def discover_new_items(api_key, inventory):
    discovered_count = 0
    max_discoveries_per_run = 3 
    
    for i in range(max_discoveries_per_run):
        existing_names = [item.get("element_name", "").lower() for item in inventory]
        target = random.choice(KEYWORDS)
        log.info(f"Discovery Phase [{i+1}/{max_discoveries_per_run}] Targeting: {target}")
        prompt = f"""
        Use Google Search to find detailed information about ONE specific Cultural Heritage, local folklore, or traditional community practice using this keyword/concept: "{target}".
        Ignore these already known elements: {existing_names[:15]}...
        
        IMPORTANT INSTRUCTIONS:
        1. The element DOES NOT need to be officially recognized by UNESCO. It can be a local tradition, unregistered heritage, rare recipe, or community practice found on local blogs or regional news.
        2. DO NOT output any links containing 'vertexaisearch.cloud.google.com' or 'grounding-api-redirect'. Output the direct, true website URL (e.g. wikipedia.org, localnews.com, etc).
        3. Analyze the element, its location, its shared heritage connections with other countries/regions, and its process/recipe.
        4. Classify the practice's relationship to Disaster Risk Reduction (DRR).
Use exactly ONE "drr_category" from this controlled vocabulary:
- Not Directly Related to DRR
- Indigenous Knowledge & Early Warning
- Ecosystem-Based Disaster Risk Reduction
- Resilient Livelihoods & Food Security
- Resilient Housing & Settlement Practices
- Traditional Emergency Preparedness
- Social Cohesion & Mutual Aid
- Climate Adaptation & Resilience
- Traditional Healing & Health Resilience
- Other Disaster Resilience Practice
Set "drr_category_valid" to true ONLY when the selected category is clearly supported by the evidence.
If there is no direct DRR connection, use "Not Directly Related to DRR".

Also classify which disaster hazards the practice directly helps address.
Use ZERO OR MORE values from exactly this vocabulary:
- Tsunami
- Earthquake
- Drought
- Flood
- Typhoon
- Wildfire
Do not infer a hazard merely because the practice exists in a disaster-prone area; select hazards only when the documented mechanism supports the connection.
Explain the mechanism in "drr_mechanism".
        5. Output ALL data values strictly in ENGLISH, and keep all JSON keys strictly in English.
5a. For "categories", select ONE OR MORE (maximum 3) of these canonical ICH thematic categories: Culinary Traditions, Traditional Craftsmanship, Performing Arts, Oral Traditions, Social Practices & Rituals. Use multiple categories only when the evidence shows the practice genuinely spans them.
        6. If you CANNOT find a detailed step-by-step process/recipe, set "resume_tata_cara" to null and "completion_status" to "INCOMPLETE".
        7. If you find all information, set "completion_status" to "COMPLETE".
        
        Output strictly as a JSON ARRAY containing ONE highly detailed object with this structure:
        [
          {{
            "id": "will_be_generated",
            "element_name": "...",
            "categories": ["Culinary Traditions"],
            "categories_valid": true,
            "category": "Culinary Traditions",
            "category_valid": true,
            "thumbnail_url": "",
            "source_urls": ["url1"],
            "scraped_at": "{datetime.now().isoformat()}Z",
            "location": {{ 
                        "country": "...", 
                        "provinces": ["..."],
                        "lat": null, 
                        "lng": null 
        }},
            "resume_analisa": {{ 
            "description": "...", 
            "cultural_significance": "...", 
            "drr_category": "Not Directly Related to DRR",
            "drr_category_valid": true,
            "drr_relevance_level": "Not Directly Related to DRR",
            "hazard_categories": [],
            "drr_mechanism": "Brief evidence-based explanation of the disaster resilience mechanism, otherwise null",
            "gemini_tags": ["..."] }},
            "resume_tata_cara": {{ "type": "...", "materials_and_tools": ["..."], "step_by_step": ["..."] }},
            "shared_heritage_detection": {{ "is_shared": true/false, "confidence_score": 0.0-1.0, "related_elements": [{{ "country": "...", "element_name": "...", "relationship_reason": "..." }}] }},
            "completion_status": "COMPLETE or INCOMPLETE"
          }}
        ]
        """
        
        new_items = call_gemini(api_key, prompt, model="gemini-2.5-flash")
        
       # PERBAIKAN: Jarak spasi di bawah ini sudah sejajar dengan 'new_items'
        if isinstance(new_items, list):
            for item in new_items:
                name = item.get("element_name", "Unknown")
                if name.lower() not in existing_names:
                    normalize_ai_classification(item)
                    item["id"] = generate_id(name)
                    
                    # --- LOGIKA KOORDINAT ---
                    loc = item.get("location", {})
                    country = loc.get("country", "")
                    provinces = loc.get("provinces", [])
                    search_query = f"{provinces[0]}, {country}" if provinces else country
                    
                    lat, lng = get_coordinates(search_query)
                    if lat is None:
                        lat, lng = get_coordinates(country)
                    
                    item["location"]["lat"] = lat
                    item["location"]["lng"] = lng
                    
                    # Logika thumbnail
                    url_to_screenshot = item.get("source_urls", [""])[0] if item.get("source_urls") else ""
                    if not item.get("thumbnail_url"):
                        item["thumbnail_url"] = get_screenshot_url(url_to_screenshot, name)
                    
                    resource_schema_defaults(item)
                    inventory.append(item)
                    discovered_count += 1
                    log.info(f"Discovered: {name} (Coords: {lat}, {lng})")
        
        time.sleep(5) 
                
    return discovered_count

# ======================================================================
# QUARTERLY JOURNAL / RESUME GENERATOR (JSON ONLY - ENGLISH)
# ======================================================================
def generate_quarterly_resume(api_key, inventory):
    # Tentukan Kuartal Saat Ini
    now = datetime.now()
    quarter_str = f"{now.year}-Q{(now.month - 1) // 3 + 1}"
    
    resume_db = {}
    
    # Load resume.json jika sudah ada
    if os.path.exists(RESUME_FILE):
        try:
            with open(RESUME_FILE, 'r', encoding='utf-8') as f:
                resume_db = json.load(f)
        except Exception:
            pass
            
    # Inisialisasi struktur untuk kuartal ini
    if quarter_str not in resume_db:
        resume_db[quarter_str] = {
            "status": "incomplete",
            "statistics": {},
            "content": {}
        }
        
    # Jika sudah complete, lewati proses
    if resume_db[quarter_str]["status"] == "complete":
        log.info(f"⏭️ Resume Jurnal untuk {quarter_str} sudah COMPLETE. Skip generasi.")
        return
        
    log.info(f"📝 Memulai penyusunan data Resume/Jurnal (Bahasa Inggris) untuk {quarter_str}...")
    
    # 1. Siapkan Statistik Data
    total_items = len(inventory)
    categories = {}
    for item in inventory:
        item_categories = item.get("categories") or [item.get("category", "Unknown")]
        for cat in item_categories:
            categories[cat] = categories.get(cat, 0) + 1
        
    resume_db[quarter_str]["statistics"] = {
        "total_items": total_items,
        "categories_distribution": categories,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Cek komparasi tren (English Version)
    previous_quarters = [q for q in resume_db.keys() if q != quarter_str]
    tren_prompt = "Focus on narrating the current cultural data collection."
    if previous_quarters:
        last_q = sorted(previous_quarters)[-1]
        tren_prompt = f"Compare with the previous quarter ({last_q}). Describe the data growth trend, focusing on developing categories and differences."

    # 2. PROMPT AI (Full English)
    prompt = f"""
    You are a Digital Anthropologist tasked with writing the Intangible Cultural Heritage Visual Journal for Quarter {quarter_str}.
    Current Statistics: Total of {total_items} cultural entities. Category distribution: {json.dumps(categories)}.
    {tren_prompt}
    
    Your task is to generate a structured narrative. Any discussion of institutional capacity, legislation, or Convention implementation MUST be explicitly framed as a data-based observation or limitation, never as verified institutional facts unless the source data supports them.
    
    The structure MUST exactly match this JSON format:
    {{
        "title": "Invisible Footprints: Visual Narrative of Cultural Heritage Quarter {quarter_str}",
        "abstract": "Abstract paragraph summarizing the findings...",
        "sections": {{
            "prologue": {{
                "title": "1. Prologue: The Common Thread of Civilization",
                "dropcap": "The first single letter of the prologue paragraph (e.g., 'W')",
                "text": "The rest of the prologue paragraph text..."
            }},
            "anatomy": {{
                "title": "2. Anatomy of Tradition: Creativity, Craft, and Spirit",
                "text": "Narrative regarding category dominance and data statistics..."
            }},
            "shared_heritage": {{
                "title": "3. Echoes Across Borders: Shared Heritage Network",
                "text": "Narrative about relationships between countries (e.g., silk, indigo dyeing, migration routes)..."
            }},
            "periodic_report": {{
                "title": "4. Status of Convention Implementation (Periodic Report)",
                "text": "Official report style similar to UNESCO Periodic Report regarding safeguarding, legislation, etc..."
            }},
            "epilogue": {{
                "title": "5. Epilogue",
                "text": "Philosophical concluding thoughts..."
            }}
        }}
    }}
    """
    
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}
    
    # Payload yang diperkuat (menggunakan responseMimeType untuk mencegah API bingung)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5, 
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        raw_text = result['candidates'][0]['content']['parts'][0]['text']
        
        # Karena menggunakan responseMimeType, AI sudah terjamin mengirim JSON bersih
        ai_content = json.loads(raw_text)
        
        # Simpan ke dalam Database Resume
        resume_db[quarter_str]["status"] = "complete"
        resume_db[quarter_str]["content"] = ai_content
        
        with open(RESUME_FILE, 'w', encoding='utf-8') as f:
            json.dump(resume_db, f, indent=4, ensure_ascii=False)
            
        log.info(f"✅ Data Jurnal {quarter_str} berhasil digenerate dan disimpan ke resume.json!")
        
    except requests.exceptions.HTTPError as http_err:
        log.error(f"❌ API Error HTTP: {http_err}")
        # Menangkap alasan spesifik dari Google jika gagal lagi
        log.error(f"Detail Penolakan Google Gemini: {response.text}") 
        with open(RESUME_FILE, 'w', encoding='utf-8') as f:
            json.dump(resume_db, f, indent=4, ensure_ascii=False)
            
    except Exception as e:
        log.error(f"❌ Gagal men-generate konten jurnal: {e}")
        with open(RESUME_FILE, 'w', encoding='utf-8') as f:
            json.dump(resume_db, f, indent=4, ensure_ascii=False)

# ======================================================================
# MAIN EXECUTION
# ======================================================================

def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        log.error("GEMINI_API_KEY not found or empty!")
        return

    try:
        db = load_db()
        inventory = db.get("inventory", [])

        # Manual workflow modes:
        #   data_only       = audit + enrichment + discovery
        #   resource_enrich = resource/value-chain/opportunity enrichment
        #   resume_only     = quarterly journal only
        #   both            = data pipeline + quarterly journal
        #
        # Scheduled runs default to data_only via crawler.yml.
        raw_crawl_mode = os.environ.get("CRAWL_MODE", "Data only").strip().lower()
        crawl_mode = raw_crawl_mode.replace(" ", "_").replace("-", "_")
        valid_modes = {"data_only", "resource_enrich", "resume_only", "both"}
        if crawl_mode not in valid_modes:
            log.warning(f"Unknown CRAWL_MODE='{crawl_mode}'. Falling back to data_only.")
            crawl_mode = "data_only"

        run_data = crawl_mode in ("data_only", "both")
        run_resource = crawl_mode == "resource_enrich"
        run_resume = crawl_mode in ("resume_only", "both")

        audited = 0
        enriched = 0
        discovered = 0

        if run_data:
            # PHASE 0: Audit Data (Downgrade status if image is missing)
            audited = audit_inventory(inventory)

            # PHASE 1: Enrich Incomplete Data First
            enriched = enrich_incomplete_items(api_key, inventory)

            # PHASE 2: Discover New Data
            discovered = discover_new_items(api_key, inventory)

            db["inventory"] = inventory

            # Save any data-pipeline modifications.
            if audited > 0 or enriched > 0 or discovered > 0:
                save_db(db)
                log.info("✅ Data pipeline complete. Audited: %s, Enriched: %s, Discovered: %s. Total DB: %s",
                         audited, enriched, discovered, len(inventory))
            else:
                log.info("Data pipeline complete. No new data added or enriched.")
        else:
            log.info("⏭️ Data discovery skipped (non-data mode).")

        if run_resource:
            schema_changed = 0
            for item in inventory:
                if resource_schema_defaults(item):
                    schema_changed += 1

            resource_result = enrich_resource_data(api_key, inventory)
            resource_enriched = resource_result["enriched"]
            resource_metadata_changed = resource_result["metadata_changed"]

            db["inventory"] = inventory
            if schema_changed > 0 or resource_metadata_changed > 0 or resource_enriched > 0:
                save_db(db)
                log.info(
                    "✅ Resource enrichment complete. Schema normalized: %s. Evidence-backed enrichments: %s. Attempt/review metadata updates: %s. Total DB: %s",
                    schema_changed,
                    resource_enriched,
                    resource_metadata_changed,
                    len(inventory)
                )
            else:
                log.info("Resource enrichment complete. No records changed.")

        if run_resume:
            # Quarterly Resume / Journal generation.
            # resume_only uses the current data.json without crawling new data.
            generate_quarterly_resume(api_key, inventory)
            log.info("✅ Resume/Journal phase complete.")
        else:
            log.info("⏭️ Quarterly Resume skipped (not requested in this mode).")

        log.info("Run Complete. Mode: %s. Total DB: %s", crawl_mode, len(inventory))

    except Exception as e:
        log.error(f"Fatal Error during main execution: {e}")
if __name__ == "__main__":
    main()