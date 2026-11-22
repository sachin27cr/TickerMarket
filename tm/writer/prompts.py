"""Prompts. The model only rewrites facts it is given; code checks every fact afterwards."""
import json


def news_prompt(cluster, today_text):
    sources = [{'outlet': i['outlet'], 'published': i['published'].strftime('%d %b %Y %H:%M IST'),
                'title': i['title'], 'summary': i['summary']} for i in cluster['items'][:6]]
    return f"""You write posts for "Ticker Market India", an Instagram news page about the Indian stock market.
Today is {today_text}. Use ONLY facts stated in the sources below. Never add a number, name, date or claim
that is not in the sources. Never give advice, predictions, targets, or opinions. Do not use words like
"reportedly", "could", "likely", "expected to". Use exact dates (e.g. "13 November 2026"), never "today".
Write in simple English an Indian retail investor understands. No emojis.

SOURCES:
{json.dumps(sources, ensure_ascii=False, indent=1)}

Return JSON with exactly these keys:
{{
 "relevant": true/false   (false if not about Indian markets, the economy, companies, IPOs, regulators, or a global event moving Indian markets; false if it is a stock tip, opinion piece or prediction),
 "category": one of "Market News","Earnings","IPO Watch","Economy","Regulation","Global Markets","Corporate Action",
 "subject": the company, organisation or index the story is about, exactly as named in the sources (e.g. "Reliance Brands", "SEBI", "Nifty 50"); "" only if it is about the whole economy,
 "headline": max 11 words; MUST name the subject (a headline like "Revenue up 3.8%" with no company is not allowed); wrap the 1-3 most important words or numbers in *single stars*; keep punctuation inside the stars when it directly follows a starred word,
 "points": 3 short key points, max 14 words each, each a fact from the sources,
 "body": 2 short paragraphs (max 45 words each) explaining what happened and why it matters, facts only,
 "hashtags": 5 relevant hashtags that are popular on Instagram for this topic,
 "companies": up to 3 NSE-listed companies the story is about, written exactly as named in the sources (empty list if none),
 "label": a 2-3 word banner for the card, no numbers, e.g. "Q2 RESULT IMPACT", "THE SELLOFF", "BIG ORDER WIN", "RBI POLICY",
 "tone": "up" if the news is about prices/results rising, "down" if falling, else "neutral",
 "sector": one of "banking","energy","it","auto","pharma","metals","oil","gold","fmcg","realty","telecom","ipo","results","economy","global","markets","other" (results = quarterly results story, markets = Sensex/Nifty/broad market move),
 "image_scene": one sentence describing a realistic photo that fits the story (a place, industry, product or object), max 30 words. No people's faces, no named or real persons, no company names, no logos, no text or numbers in the image
}}"""


def check_prompt(draft_text, cluster):
    from ..util import fmt_date, today_ist
    sources = '\n'.join(f'- [{i["outlet"]}, published {fmt_date(i["published"])}] {i["title"]}. {i["summary"]}'
                         for i in cluster['items'][:6])
    return f"""You are a strict fact-checker for a financial news page. Compare the DRAFT with the SOURCES.
Today is {fmt_date(today_ist())}; the post is dated today, so today's date and the publication dates are supported.
A full name for a short form in the sources counts as supported (M&M = Mahindra & Mahindra, Hero Moto = Hero MotoCorp,
QIBs = Qualified Institutional Buyers, RBI = Reserve Bank of India). Only flag real problems: a fact, number or name
that is NOT in the sources or contradicts them.

SOURCES:
{sources}

DRAFT:
{draft_text}

Answer in JSON:
{{
 "all_supported": true/false  (every fact, number, name and date in the draft is stated in the sources),
 "misleading": true/false     (headline or wording overstates or distorts the sources),
 "advice_or_prediction": true/false (any investment advice, recommendation or forecast),
 "issues": ["short description of each problem, empty if none"]
}}"""
