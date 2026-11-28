"""Evidence search: providers discover sources; AI only processes retrieved content."""
import os
import re
import requests

TIMEOUT = 20
MAX_RESULTS = 4

def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _search(session, provider, query, key):
    if provider == "Tavily":
        r=session.post("https://api.tavily.com/search",json={"api_key":key,"query":query,"search_depth":"basic","max_results":MAX_RESULTS,"include_answer":False,"include_raw_content":False},timeout=TIMEOUT); r.raise_for_status()
        return [{"url":x.get("url"),"title":x.get("title"),"snippet":x.get("content","")} for x in r.json().get("results",[])]
    if provider == "Exa":
        r=session.post("https://api.exa.ai/search",headers={"x-api-key":key},json={"query":query,"type":"auto","numResults":MAX_RESULTS,"contents":{"text":{"maxCharacters":1200}}},timeout=TIMEOUT); r.raise_for_status()
        return [{"url":x.get("url"),"title":x.get("title"),"snippet":x.get("text","")} for x in r.json().get("results",[])]
    if provider == "Firecrawl":
        r=session.post("https://api.firecrawl.dev/v2/search",headers={"Authorization":"Bearer "+key},json={"query":query,"limit":MAX_RESULTS,"sources":[{"type":"web"}]},timeout=TIMEOUT); r.raise_for_status()
        d=r.json().get("data",r.json()); rows=d.get("web",[]) if isinstance(d,dict) else d
        return [{"url":x.get("url"),"title":x.get("title"),"snippet":x.get("description") or x.get("markdown","")} for x in rows]
    if provider == "YOU.com":
        r=session.post("https://ydc-index.io/v1/search",headers={"X-API-Key":key},json={"query":query,"count":MAX_RESULTS,"extraction":{"extraction_mode":"highlights"}},timeout=TIMEOUT); r.raise_for_status()
        rows=(r.json().get("results") or {}).get("web",[]); out=[]
        for x in rows:
            c=x.get("contents") or {}; highlights=c.get("highlights") or x.get("snippets") or []
            out.append({"url":x.get("url"),"title":x.get("title"),"snippet":x.get("description") or " ".join(str(v) for v in highlights)})
        return out
    return []

def search_evidence(query, max_items=6):
    """Search providers in sequence, then fetch article text and Jina fallback."""
    session=requests.Session()
    provider_keys=[("Tavily",os.getenv("TAVILY_API_KEY","").strip()),("Exa",os.getenv("EXA_API_KEY","").strip()),("Firecrawl",os.getenv("FIRECRAWL_API_KEY","").strip()),("YOU.com",os.getenv("YOUCOM_API_KEY","").strip()))]
    results,seen,errors=[],set(),[]
    for provider,key in provider_keys:
        if not key: continue
        try:
            for row in _search(session,provider,query,key):
                url=row.get("url","")
                if not url.startswith(("http://","https://")) or url in seen: continue
                seen.add(url); results.append({**row,"provider":provider})
                if len(results)>=max_items: break
            print(f"Evidence search {provider}: {len(results)} source(s)")
            if len(results)>=max_items: break
        except Exception as exc:
            errors.append(f"{provider}: {str(exc)[:120]}")
            print(f"{provider} failed; trying fallback provider")
    evidence=[]
    try:
        from free_discovery import fetch_article, USER_AGENT
        session.headers.update({"User-Agent":USER_AGENT})
        for item in results[:max_items]:
            body=_clean(item.get("snippet",""))
            try:
                article=fetch_article(session,item["url"]); extracted=_clean(article.get("article_text",""))
                if len(extracted)>len(body): body=extracted
            except Exception: pass
            if len(body)<500:
                try:
                    reader=session.get("https://r.jina.ai/"+item["url"],timeout=TIMEOUT); reader.raise_for_status()
                    extracted=_clean(reader.text)
                    if len(extracted)>len(body): body=extracted
                except Exception: pass
            evidence.append({"title":item.get("title",""),"url":item["url"],"provider":item["provider"],"text":body[:4500]})
    except Exception as exc:
        errors.append("extraction: "+str(exc)[:120])
    return evidence,errors
