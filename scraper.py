"""
=======================================================================
  ICH SHARED HERITAGE RADAR v6.1 — Global Intelligence Engine
  AI Engine : Google Gemini 2.5 Flash (Google Search Grounding)
  Mode      : 2-Phase (Enrichment of Incomplete Data -> Discovery)
  Feature   : Quality over Quantity (Iterative Looping), Anti-Redundancy
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

# ======================================================================
# GLOBAL KEYWORD DATABASE FOR DISCOVERY (Multi-Language)
# ======================================================================
KEYWORDS = [
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

    "coutumes locales et traditions de village",
    "rituels traditionnels des communautés locales",
    "savoir-faire artisanal traditionnel village",
    "traditions orales transmises par les anciens",

    "民间未注册的传统习俗",
    "地方传统文化习俗",
    "民间手工艺传统技艺",
    "乡村传统节庆习俗",
    "祖传食谱与传统做法",

    "지역 숨겨진 전통 문화",
    "마을 전통 의식과 풍습",
    "전통 수공예 기술 장인",
    "세대에서 세대로 전해지는 문화",

    "local tribal rituals undocumented",
    "hidden cultural traditions village",
    "traditional ceremonies rarely documented",
    "oral folklore traditions community elders",
    "traditional crafts handmade ancestral techniques",
    "forgotten cultural rituals rural communities",
    "traditional storytelling folklore village",
    "indigenous cultural practices still alive",
    "festival desa tahunan",
    "upacara adat panen",
    "ritual pernikahan tradisional desa",
    "cara membuat kerajinan tradisional",
    "traditional harvest ceremony village",
    "ancient ritual still practiced village",
    "how villagers make traditional craft",
    "ancestral cooking method traditional dish",

    # ─────────────────────────────────────────────
    # ENGLISH (Global / General)
    # ─────────────────────────────────────────────
    "Intangible Cultural Heritage examples",
    "UNESCO 2003 Convention elements",
    "Living Heritage practices",
    "Traditional craftsmanship UNESCO",
    "Oral traditions and expressions heritage",
    "Performing arts intangible heritage",
    "ICH inventory documentation",
    "UNESCO Representative List ICH",
    "Urgent Safeguarding List ICH",
    "Traditional knowledge indigenous communities",
    "Ritual practices cultural heritage",
    "Festive events cultural heritage",
    "Traditional music instruments heritage",
    "Ancestral knowledge safeguarding",
    "Community-based heritage preservation",
    "Intangible heritage digital inventory",
    "Folk arts and traditions documentation",
    "Customary practices cultural safeguarding",
    "Social practices rituals UNESCO",
    "Nature knowledge universe heritage",
    "Traditional food preparation heritage",
    "Healing practices traditional medicine heritage",
    "Storytelling oral heritage",
    "Traditional dance heritage documentation",

    # ─────────────────────────────────────────────
    # INDONESIAN / MALAY
    # ─────────────────────────────────────────────
    "Warisan Budaya Takbenda",
    "Warisan Kebudayaan Tak Ketara",
    "Inventaris Warisan Budaya",
    "Pelestarian tradisi lisan",
    "Kesenian tradisional warisan budaya",
    "Pengetahuan tradisional masyarakat adat",
    "Upacara adat warisan budaya",
    "Keterampilan kerajinan tradisional",
    "Seni pertunjukan warisan budaya takbenda",
    "Praktik sosial budaya takbenda UNESCO",

    # ─────────────────────────────────────────────
    # SPANISH (Latin America & Spain)
    # ─────────────────────────────────────────────
    "Patrimonio Cultural Inmaterial UNESCO",
    "Patrimonio vivo tradiciones",
    "Prácticas y saberes tradicionales",
    "Inventario patrimonio inmaterial",
    "Expresiones culturales tradicionales",
    "Conocimientos ancestrales indígenas",
    "Artesanía tradicional patrimonio vivo",
    "Rituales y fiestas patrimonio UNESCO",
    "Salvaguardia patrimonio cultural inmaterial",
    "Tradiciones orales patrimonio vivo",
    "Música y danza tradicional patrimonio",
    "Medicina tradicional saberes ancestrales",

    # ─────────────────────────────────────────────
    # FRENCH (Francophone Africa, France, Canada)
    # ─────────────────────────────────────────────
    "Patrimoine culturel immatériel",
    "Traditions et expressions orales UNESCO",
    "Pratiques sociales rituels et événements festifs",
    "Inventaire patrimoine immatériel",
    "Savoir-faire artisanal traditionnel",
    "Connaissances sur la nature et l'univers",
    "Sauvegarde du patrimoine vivant",
    "Arts du spectacle patrimoine immatériel",
    "Pratiques culturelles communautaires UNESCO",
    "Expressions culturelles traditionnelles",

    # ─────────────────────────────────────────────
    # CHINESE — MANDARIN (China, Taiwan, Diaspora)
    # ─────────────────────────────────────────────
    "非物质文化遗产",          # Fēi wùzhí wénhuà yíchǎn
    "联合国教科文组织 传统手工艺",
    "口头传统和表现形式",       # Oral traditions and expressions
    "表演艺术非遗",            # Performing arts ICH
    "社会实践仪式节庆活动",     # Social practices, rituals, festive events
    "传统知识与实践",           # Traditional knowledge and practices
    "无形文化遗产保护",         # ICH safeguarding
    "民间艺术传统技艺",         # Folk art and traditional skills
    "非遗数字化记录",           # Digital documentation of ICH

    # ─────────────────────────────────────────────
    # JAPANESE
    # ─────────────────────────────────────────────
    "無形文化遺産",            # Mukei bunka isan
    "伝統的工芸技術 ユネスコ",
    "口承による伝統及び表現",   # Oral traditions and expressions
    "社会的慣習 儀式 祭礼行事",
    "自然及び万物に関する知識と慣習",
    "伝統芸能 無形文化遺産",
    "民俗芸能 無形文化",
    "無形文化遺産 保護条約",
    "伝統文化 デジタルアーカイブ",

    # ─────────────────────────────────────────────
    # KOREAN
    # ─────────────────────────────────────────────
    "무형문화유산",            # Muhyeong munhwa yusan
    "전통 지식과 관습",
    "구전 전통 및 표현",
    "공연예술 무형유산",
    "전통 공예 기술 유네스코",
    "사회적 관행 의식 및 축제",
    "무형문화재 보호",
    "전통 생활 문화 기록",

    # ─────────────────────────────────────────────
    # ARABIC (Middle East & North Africa)
    # ─────────────────────────────────────────────
    "التراث الثقافي غير المادي",       # Al-turath al-thaqafi ghayr al-madi
    "التقاليد وأشكال التعبير الشفهي",
    "الممارسات الاجتماعية والطقوس",
    "الحرف التقليدية اليدوية اليونسكو",
    "الموسيقى التقليدية التراث",
    "المعارف التقليدية والممارسات",
    "صون التراث الثقافي غير المادي",
    "فنون الأداء التراثية",
    "التراث الشفهي والموروث الثقافي",
    "قوائم جرد التراث غير المادي",

    # ─────────────────────────────────────────────
    # PORTUGUESE (Brazil, Portugal, Lusophone Africa)
    # ─────────────────────────────────────────────
    "Patrimônio Cultural Imaterial",
    "Saberes e práticas tradicionais",
    "Inventário patrimônio imaterial",
    "Expressões culturales tradicionais",
    "Conhecimentos ancestrais indígenas",
    "Artesanato tradicional patrimônio",
    "Rituais e festas patrimônio UNESCO",
    "Tradições orais patrimônio imaterial",
    "Salvaguarda patrimônio cultural vivo",
    "Artes do espetáculo patrimônio imaterial"
]

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
        cat = item.get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1
        
    return {
        "generated_at": datetime.now().isoformat() + "Z",
        "total_ich_elements": len(inventory),
        "complete_records": complete,
        "incomplete_records": incomplete,
        "categories_breakdown": categories
    }

def get_screenshot_url(url):
    if not url or url.lower() == "n/a":
        return "N/A"
    encoded_url = requests.utils.quote(url)
    return f"https://api.microlink.io/?url={encoded_url}&screenshot=true&meta=false&embed=screenshot.url"

def generate_id(name):
    return "ich-" + hashlib.md5(name.lower().encode()).hexdigest()[:8]

# ======================================================================
# CORE: GEMINI AI INTERACTION
# ======================================================================

def call_gemini(api_key, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {
            "temperature": 0.4, # Lower temperature for strictly formatted output
            "maxOutputTokens": 8192
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        if response.status_code != 200:
            log.error(f"Google API Error: {response.text}")
            return None

        data = response.json()
        text = data['candidates'][0]['content']['parts'][0]['text']
        
        # Extract JSON from Markdown code blocks
        clean_text = text.replace('```json', '').replace('```', '')
        start_idx = clean_text.find('[') if '[' in clean_text else clean_text.find('{')
        end_idx = clean_text.rfind(']') if clean_text.rfind(']') > clean_text.rfind('}') else clean_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            return json.loads(clean_text[start_idx:end_idx+1])
        return None
    except Exception as e:
        log.error(f"Gemini API failure: {e}")
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
    
    # Process up to 3 incomplete items per run to save quota
    for item in incomplete_items[:3]:
        element_name = item.get("element_name")
        current_sources = item.get("source_urls", [])
        
        log.info(f"Enriching: {element_name}")
        
        prompt = f"""
        You are a Cultural Heritage expert. I have an incomplete record for the Cultural Heritage practice/tradition: "{element_name}".
        Current known sources: {current_sources}.
        
        Please use Google Search to find the missing information (e.g., specific step-by-step crafting process, authentic recipe, or detailed history). 
        You can search through local news, community blogs, and social media.
        Find AT LEAST ONE NEW source URL to add to the existing ones.
        
        IMPORTANT: DO NOT output any links containing 'vertexaisearch.cloud.google.com' or 'grounding-api-redirect'. Output the direct, true website URL.
        
        Respond ONLY with a JSON object representing the UPDATED element.
        Ensure ALL output data values and keys are strictly in ENGLISH.
        If you find the missing data, change "completion_status" to "COMPLETE".
        
        Required JSON Structure:
        {{
            "id": "{item.get('id')}",
            "element_name": "{element_name}",
            "category": "{item.get('category', 'Traditional Craftsmanship')}",
            "thumbnail_url": "{item.get('thumbnail_url')}",
            "source_urls": ["<old_url>", "<new_found_url>"],
            "scraped_at": "{datetime.now().isoformat()}Z",
            "location": {{ "country": "...", "provinces": ["..."] }},
            "resume_analisa": {{ "description": "...", "cultural_significance": "...", "gemini_tags": ["..."] }},
            "resume_tata_cara": {{ "type": "crafting_process/culinary_recipe/ritual_sequence", "materials_and_tools": ["..."], "step_by_step": ["..."] }},
            "shared_heritage_detection": {{ "is_shared": true, "confidence_score": 0.95, "related_elements": [{{ "country": "...", "element_name": "...", "relationship_reason": "..." }}] }},
            "completion_status": "COMPLETE"
        }}
        """
        
        updated_item = call_gemini(api_key, prompt)
        if updated_item and isinstance(updated_item, dict) and "resume_tata_cara" in updated_item:
            # Merge logic
            index = inventory.index(item)
            inventory[index] = updated_item
            enriched_count += 1
            log.info(f"Successfully enriched {element_name} from multiple sources.")
        
        time.sleep(5) # Rate limit safety (Jeda 5 detik antar request)
        
    return enriched_count

# ======================================================================
# PHASE 2: DISCOVERY (Finding New Data)
# ======================================================================

def discover_new_items(api_key, inventory):
    discovered_count = 0
    
    # LOOPING BATCH: Bertanya hingga 3 kali untuk menjaga Kualitas (Quality Over Quantity)
    # Daripada meminta AI muntahin 5 sekaligus, kita minta 1 per 1 diulang 3x.
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
        4. Output ALL data values strictly in ENGLISH, and keep all JSON keys strictly in English.
        5. If you CANNOT find a detailed step-by-step process/recipe, set "resume_tata_cara" to null and "completion_status" to "INCOMPLETE".
        6. If you find all information, set "completion_status" to "COMPLETE".
        
        Output strictly as a JSON ARRAY containing ONE highly detailed object with this structure:
        [
          {{
            "id": "will_be_generated",
            "element_name": "...",
            "category": "Culinary Traditions | Traditional Craftsmanship | Performing Arts | Oral Traditions | Social Practices & Rituals",
            "thumbnail_url": "",
            "source_urls": ["url1"],
            "scraped_at": "{datetime.now().isoformat()}Z",
            "location": {{ "country": "...", "provinces": ["..."] }},
            "resume_analisa": {{ "description": "...", "cultural_significance": "...", "gemini_tags": ["..."] }},
            "resume_tata_cara": {{ "type": "...", "materials_and_tools": ["..."], "step_by_step": ["..."] }},
            "shared_heritage_detection": {{ "is_shared": true/false, "confidence_score": 0.0-1.0, "related_elements": [{{ "country": "...", "element_name": "...", "relationship_reason": "..." }}] }},
            "completion_status": "COMPLETE or INCOMPLETE"
          }}
        ]
        """
        
        new_items = call_gemini(api_key, prompt)
        
        if isinstance(new_items, list):
            for item in new_items:
                name = item.get("element_name", "Unknown")
                if name.lower() not in existing_names:
                    item["id"] = generate_id(name)
                    # Ensure thumbnail
                    if not item.get("thumbnail_url") and item.get("source_urls"):
                        item["thumbnail_url"] = get_screenshot_url(item["source_urls"][0])
                    
                    inventory.append(item)
                    discovered_count += 1
                    log.info(f"Discovered new element: {name} (Status: {item.get('completion_status')})")
        
        # Beri jeda 5 detik antar pencarian agar aman dari pemblokiran API (Rate Limits)
        time.sleep(5) 
                
    return discovered_count

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
        
        # PHASE 1: Enrich Incomplete Data First
        enriched = enrich_incomplete_items(api_key, inventory)
        
        # PHASE 2: Discover New Data
        discovered = discover_new_items(api_key, inventory)
        
        db["inventory"] = inventory
        
        # Save if there's any modification
        if enriched > 0 or discovered > 0:
            save_db(db)
            log.info(f"✅ Run Complete. Enriched: {enriched}, Discovered: {discovered}. Total DB: {len(inventory)}")
        else:
            log.info("Run Complete. No new data added or enriched.")

    except Exception as e:
        log.error(f"Fatal Error during main execution: {e}")

if __name__ == "__main__":
    main()
