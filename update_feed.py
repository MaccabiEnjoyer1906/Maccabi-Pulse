#!/usr/bin/env python3
"""Hourly public-feed updater for Maccabi Pulse."""
import json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from deep_translator import GoogleTranslator

ROOT=Path(__file__).parent
QUERIES=[
 ('מכבי תל אביב כדורגל העברות', 'he', 'transfer'),
 ('Maccabi Tel Aviv FC transfer', 'en', 'transfer'),
 ('Maccabi Tel Aviv FC football -basketball -EuroLeague', 'en', 'news'),
]
TRUST={'maccabi-tlv.co.il':('official','Official'),'sports.walla.co.il':('strong','Strong report'),'sport1.maariv.co.il':('strong','Strong report'),'one.co.il':('strong','Strong report'),'ynet.co.il':('strong','Strong report')}

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'MaccabiPulse/1.0 (+public GitHub Pages feed)'})
 return urllib.request.urlopen(req,timeout=25).read()
def clean(s): return re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',s or '')).strip()
def host_from_google_link(link):
 # Google News RSS descriptions/titles carry publisher; source URL may remain redirected.
 return urllib.parse.urlparse(link).netloc.lower().removeprefix('www.')
def translate(text,lang):
 if lang!='he' or not re.search('[\u0590-\u05ff]',text): return text,False
 try:return GoogleTranslator(source='he',target='en').translate(text),True
 except Exception:return text,False

def football_relevant(title, desc, source):
 text=(title+' '+desc+' '+source).lower()
 blocked=['basketball','euroleague','euro league','nba','hoops','basketnews','roundball','יורוליג','כדורסל']
 if any(x in text for x in blocked): return False
 signals=['maccabi tel aviv fc','maccabi tel-aviv fc','football','soccer','transfer','signing','loan','winger','striker','midfielder','defender','goalkeeper','manager','premier league','uefa','מכבי תל אביב','כדורגל','העברות']
 return any(x in text for x in signals)

def main():
 old=json.loads((ROOT/'data.json').read_text()) if (ROOT/'data.json').exists() else {'stories':[]}
 out=[];seen=set()
 for query,lang,kind in QUERIES:
  url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'he' if lang=='he' else 'en-US','gl':'IL','ceid':'IL:'+lang})
  try: root=ET.fromstring(get(url))
  except Exception as e: print('feed failed',query,e);continue
  for it in root.findall('.//item')[:25]:
   title=clean(it.findtext('title'));link=clean(it.findtext('link'));desc=clean(it.findtext('description'));pub=clean(it.findtext('pubDate'));source=clean(it.findtext('source')) or 'Google News source'
   if not football_relevant(title,desc,source): continue
   try:
    from email.utils import parsedate_to_datetime
    dt=parsedate_to_datetime(pub)
    if dt < datetime.now(timezone.utc)-timedelta(days=45): continue
   except Exception: pass
   key=re.sub(r'\W+','',title.lower())[:120]
   if not title or key in seen:continue
   seen.add(key); en_title,tr1=translate(title,lang);en_desc,tr2=translate(desc,lang)
   # Never publish untranslated Hebrew. Keep the previous English feed if translation is unavailable.
   if re.search('[\u0590-\u05ff]',en_title+' '+en_desc): continue
   src_domain=''; src_el=it.find('source')
   if src_el is not None:src_domain=urllib.parse.urlparse(src_el.attrib.get('url','')).netloc.lower().removeprefix('www.')
   level,label=TRUST.get(src_domain,('early','Early rumor'))
   if src_domain=='maccabi-tlv.co.il':kind='official'
   why='Club announcement.' if level=='official' else ('Established outlet; still unconfirmed by the club.' if level=='strong' else 'Single-source signal; treat as unconfirmed until corroborated.')
   out.append({'id':key,'kind':kind,'level':level,'label':label,'source':source,'translated':tr1 or tr2,'time':pub[:16] if pub else 'New','title':en_title,'body':en_desc[:320] or 'Open the original report for details.','why':'Why this label: '+why,'url':link})
 # keep newest fetched plus seeded fallbacks; normalize dedupe by title
 for x in old.get('stories',[]):
  if not football_relevant(x.get('title',''),x.get('body',''),x.get('source','')): continue
  key=re.sub(r'\W+','',x.get('title','').lower())[:120]
  if key not in seen:out.append(x);seen.add(key)
 payload={'updated_at':datetime.now(timezone.utc).isoformat(),'stories':out[:50]}
 (ROOT/'data.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
 print('wrote',len(payload['stories']),'stories')
if __name__=='__main__':main()
