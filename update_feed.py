#!/usr/bin/env python3
"""Hourly public-feed updater for Maccabi Pulse."""
import json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from deep_translator import GoogleTranslator

ROOT=Path(__file__).parent
# (query, language, default kind, is this a Fabrizio-Romano-tracking query)
QUERIES=[
 ('מכבי תל אביב כדורגל העברות', 'he', 'transfer', False),
 ('Maccabi Tel Aviv FC transfer', 'en', 'transfer', False),
 ('Maccabi Tel Aviv FC football -basketball -EuroLeague', 'en', 'news', False),
 ('"Fabrizio Romano" "Maccabi Tel Aviv"', 'en', 'transfer', True),
 ('"פבריציו רומאנו" "מכבי תל אביב"', 'he', 'transfer', True),
]
TRUST={'maccabi-tlv.co.il':('official','Official'),'sports.walla.co.il':('strong','Strong report'),'sport1.maariv.co.il':('strong','Strong report'),'one.co.il':('strong','Strong report'),'ynet.co.il':('strong','Strong report')}
STALE=timedelta(days=45)
HEBREW=re.compile('[\u0590-\u05ff]')

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'MaccabiPulse/1.0 (+public GitHub Pages feed)'})
 return urllib.request.urlopen(req,timeout=25).read()
def clean(s): return re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',s or '')).strip()
def translate(text,lang):
 if lang!='he' or not HEBREW.search(text): return text,False
 try:return GoogleTranslator(source='hebrew',target='en').translate(text),True
 except Exception:return text,False

def parse_dt(s):
 if not s:return None
 try:
  dt=datetime.fromisoformat(str(s).replace('Z','+00:00'))
  if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
  return dt
 except Exception:pass
 try:
  dt=parsedate_to_datetime(s)
  if dt and dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
  return dt
 except Exception:pass
 for fmt in ('%a, %d %b %Y','%b %d, %Y','%b %d'):
  try:
   dt=datetime.strptime(s,fmt)
   return dt.replace(year=dt.year if '%Y' in fmt else datetime.now(timezone.utc).year,tzinfo=timezone.utc)
  except Exception:pass
 return None

def display_time(dt,pub):
 if dt:return dt.strftime('%b %d').replace(' 0',' ')
 return (pub or '')[:16] or 'New'

def is_romano_text(title,desc,source):
 return re.search(r'fabrizio\s+romano|פבריציו\s+רומאנו',(title+' '+desc+' '+source).lower()) is not None

def football_relevant(title, desc, source):
 text=(title+' '+desc+' '+source).lower()
 blocked=['basketball','euroleague','euro league','eurocup','nba','hoops','basketnews','roundball','volleyball','handball','יורוליג','יורוקאפ','כדורסל','כדורעף','כדוריד']
 if any(x in text for x in blocked): return False
 signals=['maccabi tel aviv fc','maccabi tel-aviv fc','maccabi tel aviv','maccabi tel-aviv','football','soccer','transfer','signing','loan','winger','striker','midfielder','defender','goalkeeper','manager','premier league','uefa','מכבי תל אביב','כדורגל','העברות']
 return any(x in text for x in signals)

def story_dt(s):return parse_dt(s.get('ts','') or '') or parse_dt(s.get('time','') or '')

def main():
 old=json.loads((ROOT/'data.json').read_text()) if (ROOT/'data.json').exists() else {'stories':[]}
 now=datetime.now(timezone.utc)
 out=[];seen=set()
 for query,lang,kind,romano_q in QUERIES:
  url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'he' if lang=='he' else 'en-US','gl':'IL','ceid':'IL:'+lang})
  try: root=ET.fromstring(get(url))
  except Exception as e: print('feed failed',query,e);continue
  for it in root.findall('.//item')[:25]:
   title=clean(it.findtext('title'));link=clean(it.findtext('link'));desc=clean(it.findtext('description'));pub=clean(it.findtext('pubDate'));source=clean(it.findtext('source')) or 'Google News source'
   if not football_relevant(title,desc,source): continue
   dt=parse_dt(pub)
   if dt and dt < now-STALE: continue
   key=re.sub(r'\W+','',title.lower())[:120]
   if not title or key in seen:continue
   seen.add(key); en_title,tr1=translate(title,lang);en_desc,tr2=translate(desc,lang)
   # Never publish untranslated Hebrew. Keep the previous English feed if translation is unavailable.
   if HEBREW.search(en_title+' '+en_desc): continue
   src_domain=''; src_el=it.find('source')
   if src_el is not None:src_domain=urllib.parse.urlparse(src_el.attrib.get('url','')).netloc.lower().removeprefix('www.')
   level,label=TRUST.get(src_domain,('early','Early rumor'))
   if src_domain=='maccabi-tlv.co.il':kind='official'
   romano=romano_q or is_romano_text(title,desc,source)
   if romano and level!='official':level,label='strong','Romano report'
   if level=='official':why='Club announcement.'
   elif romano:why='Linked to Fabrizio Romano’s reporting; credible, but not confirmed by the club.'
   elif level=='strong':why='Established outlet; still unconfirmed by the club.'
   else:why='Single-source signal; treat as unconfirmed until corroborated.'
   story={'id':key,'kind':kind,'level':level,'label':label,'source':source,'translated':tr1 or tr2,'time':display_time(dt,pub),'title':en_title,'body':en_desc[:320] or 'Open the original report for details.','why':'Why this label: '+why,'url':link}
   if dt:story['ts']=dt.isoformat()
   if romano:story['romano']=True
   out.append(story)
 # keep previously saved stories that are still relevant and fresh; normalize dedupe by title
 for x in old.get('stories',[]):
  if not football_relevant(x.get('title',''),x.get('body',''),x.get('source','')): continue
  dt=story_dt(x)
  if dt and dt < now-STALE: continue
  # Translate or drop saved stories that still carry untranslated Hebrew.
  if HEBREW.search(x.get('title','')+' '+x.get('body','')):
   t1,_=translate(x.get('title',''),'he');t2,_=translate(x.get('body',''),'he')
   if HEBREW.search(t1+' '+t2): continue
   x['title'],x['body'],x['translated']=t1,t2[:320],True
  if dt:
   if 'ts' not in x:x['ts']=dt.isoformat()
   x['time']=display_time(dt,'')
  key=re.sub(r'\W+','',x.get('title','').lower())[:120]
  if key not in seen:
   x['id']=key;out.append(x);seen.add(key)
 # newest first, older below; stories without a parseable date sink to the bottom
 out.sort(key=lambda s:(story_dt(s) or datetime(1970,1,1,tzinfo=timezone.utc)).timestamp(),reverse=True)
 payload={'updated_at':now.isoformat(),'stories':out[:50]}
 (ROOT/'data.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
 print('wrote',len(payload['stories']),'stories')
if __name__=='__main__':main()
