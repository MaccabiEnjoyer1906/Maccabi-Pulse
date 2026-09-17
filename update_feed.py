#!/usr/bin/env python3
"""Hourly public-feed updater for Maccabi Pulse: full Maccabi Tel Aviv FC football coverage."""
import json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from deep_translator import GoogleTranslator

ROOT=Path(__file__).parent
# (query, language, default kind, is this a Fabrizio-Romano-tracking query)
QUERIES=[
 # transfers (kept)
 ('מכבי תל אביב כדורגל העברות', 'he', 'transfer', False),
 ('Maccabi Tel Aviv FC transfer', 'en', 'transfer', False),
 # general club football news
 ('Maccabi Tel Aviv FC football -basketball -EuroLeague', 'en', 'news', False),
 ('מכבי תל אביב כדורגל', 'he', 'news', False),
 # matches: previews, recaps, scores
 ('Maccabi Tel Aviv FC match report OR preview OR score', 'en', 'match', False),
 ('מכבי תל אביב משחק תוצאה', 'he', 'match', False),
 # injuries and squad/lineup news
 ('Maccabi Tel Aviv injury lineup squad', 'en', 'injury', False),
 ('מכבי תל אביב פצוע הרכב סגל', 'he', 'injury', False),
 # coach and player interviews
 ('Maccabi Tel Aviv coach interview press conference', 'en', 'interview', False),
 ('מכבי תל אביב ראיון מאמן שחקן', 'he', 'interview', False),
 # standings and league race
 ('Maccabi Tel Aviv standings league table', 'en', 'standings', False),
 ('מכבי תל אביב טבלת הליגה', 'he', 'standings', False),
 # European competition
 ('Maccabi Tel Aviv Conference League Europa League', 'en', 'europe', False),
 ('מכבי תל אביב אירופה קונפרנס ליג', 'he', 'europe', False),
 # official club announcements
 ('Maccabi Tel Aviv FC official announcement', 'en', 'news', False),
 ('מכבי תל אביב הודעה רשמית', 'he', 'news', False),
 # Fabrizio Romano tracking
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
 alltext=(title+' '+desc+' '+source).lower()
 text=(title+' '+desc).lower()
 blocked=['basketball','euroleague','euro league','eurocup','nba','hoops','basketnews','roundball','volleyball','handball','u19','u21','under-19','under-21','יורוליג','יורוקאפ','כדורסל','כדורעף','כדוריד','נוער']
 if any(x in alltext for x in blocked): return False
 # other Maccabi clubs are fine only when the story is actually about Maccabi Tel Aviv (e.g. a head-to-head match)
 other_clubs=['maccabi haifa','maccabi netanya','maccabi petah','maccabi bnei','bnei reineh','maccabi herzliya','maccabi jaffa','maccabi kabilio','מכבי חיפה','מכבי נתניה','מכבי פתח','מכבי בני','מכבי הרצליה','מכבי יפו']
 if any(x in alltext for x in other_clubs) and not re.search(r'maccabi tel.?aviv|מכבי תל אביב',text): return False
 # require the club or clear football terms in the story itself, not just the outlet name
 signals=['maccabi tel aviv','maccabi tel-aviv','מכבי תל אביב']
 if any(x in text for x in signals): return True
 # the club's own site is authoritative even when the headline does not repeat the club name
 if 'maccabi tel aviv' in source.lower() or 'מכבי תל אביב' in source: return True
 # trusted Israeli outlets use bare 'Maccabi' for Maccabi Tel Aviv in football coverage
 trusted=['walla','sport1','sport5','one.co','ynet','jpost','jerusalem post','maariv','keshet','13tv','kan ']
 if any(t in source.lower() for t in trusted) and re.search(r'\bmaccabi\b|מכבי',text): return True
 return False

def classify(title, desc, default):
 """Assign the best category from English text; default kind from the query wins only ties."""
 text=(title+' '+desc).lower()
 if re.search(r'injur|sideline|ruled out|rules out|fitness doubt|doubtful|\bknock\b|strain|\btear\b|recovery|rehab',text): return 'injury'
 if re.search(r'lineup|starting xi|starting line|first xi|squad list|called up|call-up|suspen|roster|bench',text): return 'squad'
 if re.search(r'match report|match preview|preview|recap|highlights|full.time|half.time|score|scorer|brace|hat-trick|hat trick|win over|won|victory|beat|beats|defeat|draw|fixture|kick.?off|derby|eliminated|penalties|vs\.? | v ',text): return 'match'
 if re.search(r'interview|press conference|said|speaks|spoke|told reporters|quotes|on the eve',text): return 'interview'
 if re.search(r'standings|league table|points race|top of the table|league leaders|championship race|title race|playoff',text): return 'standings'
 if re.search(r'conference league|europa league|champions league|uefa|european|group stage|knockout',text): return 'europe'
 if re.search(r'transfer|signing|signs|signed|loan|deal|clause|contract|extension|medical|bid|offer|target|winger|striker|joins|joined|window|depart|exit|agreement',text): return 'transfer'
 return default if default in ('news','match','injury','interview','standings','europe') else 'news'

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
   story_kind=classify(en_title,en_desc,kind)
   if src_domain=='maccabi-tlv.co.il':story_kind='official'
   romano=romano_q or is_romano_text(title,desc,source)
   if romano and level!='official':level,label='strong','Romano report'
   if level=='official':why='Club announcement.'
   elif romano:why='Linked to Fabrizio Romano’s reporting; credible, but not confirmed by the club.'
   elif level=='strong':why='Established outlet; still unconfirmed by the club.'
   else:why='Single-source signal; treat as unconfirmed until corroborated.'
   story={'id':key,'kind':story_kind,'level':level,'label':label,'source':source,'translated':tr1 or tr2,'time':display_time(dt,pub),'title':en_title,'body':en_desc[:320] or 'Open the original report for details.','why':'Why this label: '+why,'url':link}
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
  if x.get('kind') not in ('official','match','squad','injury','interview','standings','europe','transfer','news') or x.get('kind')=='news':
   x['kind']=classify(x.get('title',''),x.get('body',''),'news')
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
from collections import Counter
if __name__=='__main__':
 main()
 d=json.loads((ROOT/'data.json').read_text())
 print(Counter(s['kind'] for s in d['stories']))
