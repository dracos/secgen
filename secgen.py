#!/guest/matthew/.virtualenvs/base/bin/python
#
# secgen.py:
# Twitter the daily schedule of the UN Secretary-General
#
# Copyright (c) 2007 Matthew Somerville.
# http://www.dracos.co.uk/

import argparse
import os
import re
import textwrap
import requests
import htmlentitydefs
import arrow
from time import sleep
from BeautifulSoup import BeautifulSoup
import tweepy
from config import *

localfile = '/guest/matthew/data/secgen-schedule'

REGEX_TIME = re.compile('(\*?(\d+)(?:(?::|\.)\s*(\d+)|\s*(a\.?m\.?|p\.?m\.?|noon))+\.?\s*\*?)')

def main():
    p = argparse.ArgumentParser(description="UN Secretary-General > Twitter v1.0")
    choices = [ 'fetch', 'twitter', 'test' ]
    p.add_argument('action', choices=choices,
            help='Action to perform; one of %s' % ', '.join(choices) )
    options = p.parse_args()

    if options.action == 'fetch':
        if fetch():
            test(fetched=1)
    elif options.action == 'twitter':
        now = arrow.utcnow()
        for time, event in parse():
            if now >= time and now < time.replace(minutes=5):
                twitter(event)
    elif options.action == 'test':
        test()
    else:
        p.print_help()

def test(fetched=0):
    for time, event in parse(warn=1):
        if fetched:
            print "New schedule downloaded"
            fetched = 0
        print time, event.encode('utf-8')

def remove_changing_bits(s):
    return re.sub('^.*?view-content(?s)', '', s)

def diff(a, b):
    return remove_changing_bits(a) != remove_changing_bits(b)

def fetch():
    new = get_contents('https://www.un.org/sg/en/content/sg/appointments-secretary-general')
    if not new:
        return False
    current = ''
    try:
        current = get_contents(localfile)
    except:
        pass
    if diff(current, new) and not re.search('Proxy Error|urgent maintenance|Not Found|Service Temporarily Unavailable|Internal server error|HTTP Error 50[17]|SQLState(?i)', new):
        f = open(localfile, 'w')
        f.write(new)
        f.close()
        try:
            os.remove('%s-override' % localfile)
        except:
            pass
        return True
    return False

def parse(warn=0):
    try:
        d = get_contents("%s-override" % localfile)
    except IOError:
        try:
            d = get_contents(localfile)
        except IOError:
            if warn:
                print 'No downloaded schedule'
            return []
    soup = BeautifulSoup(d, smartQuotesTo=None)
    table = soup.find('div', 'view-schedules')
    if not table:
        return []
    events = []
    pastnoon = False
    date = arrow.get(table.find('span', 'date-display-single')['content'], 'YYYY-MM-DDTHH:mm:ssZZ')
    for row in table('tr'):
        row = parsecell(row.renderContents().decode('utf-8'))
        m = REGEX_TIME.match(row)
        if not m:
            if row[0:2] in ('- ', 'Mr') or row[0:4] == 'Amb.':
                event = parsecell(row, True)
                last = events[-1]
                events[-1] = ( last[0], '%s %s' % (last[1], event) )
            continue
        time = m.group(1)
        text = row.replace(time, '')
        time, pastnoon = parsetime(time, date, pastnoon)
        event = parsecell(text, True)
        event = prettify(event)
        events.append((time, event))
    return events

def twitter(s):
    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    api = tweepy.API(auth)

    if len(s)>280:
        wrapped = textwrap.wrap(s, 280-2)
    else:
        wrapped = [ s ]
    resp = ''
    first = True
    in_reply_to_status_id = None
    for line in wrapped:
        if resp:
            sleep(5)
        if first and len(wrapped)>1:
            line = u"%s\u2026" % line
        if not first:
            line = u"\u2026%s" % line
        update = api.update_status(line, in_reply_to_status_id)
        in_reply_to_status_id = update.id
        resp += update.text
        first = False
    return resp

def parsetime(time, date, pastnoon):
    m = REGEX_TIME.search(time)
    if m:
        (dummy, hour, min, pm) = m.groups()
        if min == None:
            min = 0
        if len(hour) == 3:
            hour, min = hour[0], hour[1:]
    elif time == 'noon':
        hour = 12
        min = 0
        pm = 'noon'
    hour = int(hour)
    min = int(min)
    if not pm and pastnoon:
        hour += 12
    if pm in ('pm', 'p.m', 'p.m.') and hour < 12:
        hour += 12
    if pm in ('am', 'a.m', 'a.m.') and hour == 12:
        hour -= 12
    if pm in ('pm', 'p.m', 'p.m.', 'noon'):
        pastnoon = True
    d = date.replace(hour=hour, minute=min)
    return d, pastnoon

def prettify(s):
    if re.match('Addressing|Meeting (with|on)|Visiting|Visit to|Trilateral Meeting', s) and not re.search('Secretary-General (will|to) make remarks', s):
        return s
    if re.match('Chairing of the ', s):
        return re.sub('Chairing of the ', 'Chairing the ', s)
    if re.match('Joint press encounter by the Secretary-General with: ', s):
        return re.sub('Joint press encounter by the Secretary-General with: ', 'Joint press encounter with ', s)
    if re.match('Joint Declaration on (.*?) by the Secretary-General and ', s):
        return re.sub('Joint (.*?) by the Secretary-General and ', r'Joint \1 with ', s)
    if re.match('(The )?Secretary-General[^a-zA-Z]*(to|will) address ', s):
        return re.sub('(The )?Secretary-General[^a-zA-Z]*(to|will) address ', 'Addressing ', s)
    if re.match('(The )?Secretary-General (to|will) make ', s):
        return re.sub('(The )?Secretary-General (to|will) make ', 'Making ', re.sub(r'\bhis\b', 'my', s))
    if re.match('Secretary-General to attend ', s):
        return re.sub('Secretary-General to attend ', 'Attending ', s)
    if re.match('.*? hosted by the Secretary-General ', s):
        return re.sub('(.*?) hosted by the Secretary-General ', r'Hosting \1 ', s)
    if re.match('Secretary-General to host ', s):
        return re.sub('Secretary-General to host ', 'Hosting ', s)
    if re.match('Secretary-General to brief ', s):
        return re.sub('Secretary-General to brief ', 'Briefing ', s)
    if re.search('to hear a briefing by the Secretary-General', s):
        return 'Briefing a ' + re.sub('to hear a briefing by the Secretary-General ', '', s)
    if re.match('Secretary-General&rsquo;s briefing to ', s):
        return re.sub('Secretary-General&rsquo;s briefing to ', 'Briefing to ', s)
    if re.match('Secretary-General to speak at ', s):
        return re.sub('Secretary-General to speak at ', 'Speaking at ', s)
    if re.match('Secretary-General to speak to ', s):
        return re.sub('Secretary-General to speak to ', 'Speaking to ', s)
    if re.match('Secretary-General\'s opening statement at ', s):
        return re.sub('Secretary-General\'s opening statement at his ', 'Making opening statement at my ', s)
    if re.match('Secretary-General\'s closing statement at ', s):
        return re.sub('Secretary-General\'s closing statement at his ', 'Making closing statement at my ', s)
    if re.match('Secretary-General to deliver ', s):
        return re.sub('Secretary-General to deliver ', 'Delivering ', s)
    if re.match('Secretary-General will hold ', s):
        return re.sub('Secretary-General will hold ', 'Holding ', s)
    if re.match('Secretary-General to give ', s):
        return re.sub('Secretary-General to give ', 'Giving ', s)
    if re.match('Remarks by the Secretary-General |SG remarks at|Secretary(-| )General\'?s? (to (make|give) )?remarks |Welcoming Remarks ', s):
        return re.sub('Remarks by the Secretary-General |SG remarks |Secretary(-| )General\'?s? (to (make|give) )?remarks |Welcoming Remarks ', 'Making remarks ', s)
    m = re.search(' (?:.\200\223 |- |\[|{|\()Secretary-General (?:to|will) make ([Oo]pening |closing )?[rR]emarm?ks(\]|}|\))?\.?$', s)
    if m:
        new = 'Making %sremarks at ' % (m.group(1) or '').lower()
        s = re.sub('^Addressing ', '', s)
        if not re.match('The (?i)', s): new += 'the '
        return re.sub('^(.*) (?:.\200\223 |- |\[|{|\()Secretary-General (?:to|will) make ([Oo]pening |closing )?[rR]emarm?ks(\]|}|\))?', new + r'\1', s)
    if re.match('\[Remarks at\] ', s):
        return re.sub('\[Remarks at\] ', 'Making remarks at ', s)
    if re.search('Presentation of credential(?i)', s) or re.match('Remarks at', s) or re.match('Election of', s) or re.match('Swearing[ -]in Ceremony', s):
        pass
    elif re.search('(?<!on )Youth$|^Group of Friends|^Leaders|^Chairmen|^Permanent Representatives?|^Executive Secretaries|Board members|Contact Group|Envoys|Team$|^Honou?rable|Interns|Order|Board of Trustees|Journalists|Committee$|Fellows$|^(UN )?Youth Delegates', s) and not re.search('(president|photo opportunity|concert|luncheon|breakfast|event)(?i)', s) and not re.match('Meeting of|Joint meeting', s):
        s = 'Meeting the %s' % s
    elif re.match('- Mr|His (Royal|Serene) Highness|President|Association of|Vuk|Queen|Prince|Major-General|His Excellency|His Eminence|His Holiness|His Majesty|Her Majesty|Ambassador|H\.?R\.?H|H\. ?M\.|H\. ?H\.|H\.? ?E\.?|S\. ?E\.|Rev\.|The Very Rev|Sir|General (?!Assembly)|H\.S\.H|\.?Mr\.?|Mrs\.|Prof\.|Dr\.?|Lord|Lady|Justice|Professor|Ms\.?|Amb\.?|Mayor|Messrs\.|Senator|(The )?R(igh)?t\.? Hon(ou?rable)?\.?|The Hon\.|Hon\.|U\.S\. House|U\.S\. Senator|US Congressman|Judge|Cardinal|Archbishop|The Honou?rable|Rabbi|Lt\.|Major General|Lieutenant|Excelent|Metropolitan|Psy|Thura|Lang Lang|Bahey|Antti|Bishop|Pastor|Shaykh|Srgjan|Michel', s) and not re.search('luncheon(?i)', s):
        s = re.sub('Amb\.', 'Ambassador', s)
        s = re.sub('^Amb ', 'Ambassador ', s)
        if re.match('The ', s):
            s = re.sub('^The', 'the', s)
        s = 'Meeting %s' % s
    elif re.search('Delegation|Members(?i)', s) and not re.search('(Joint Meeting|Group Meeting|concert|luncheon|breakfast)(?i)', s):
        s = 'Meeting the %s' % s
    elif re.search(r'Elder|High Representative|Chairman\b|Secretary-General of the League|Senior Adviser|Special Adviser|Special Representative|Permanent Representative|Minister of|Secretary of State for|Administrator|CEO|National Adviser|Ambassador|students|Students', s) and not re.search('(concert|conversation|luncheon|breakfast|hosted by|hand-over|meeting|conference)(?i)', s):
        s = 'Meeting %s' % s
    elif re.match('The ', s):
        s = re.sub('^The ', 'Attending the ', s)
    else:
        s = 'Attending the %s' % s
    return s

def parsecell(s, d=False):
    s = re.sub('\xc2\xa0', ' ', s)
    s = re.sub(u'\xa0', ' ', s)
    if d:
        s = re.sub("<br />", ", ", s)
        s = re.sub("</p>", " ", s)
    s = re.sub("<[^>]*>", "", s)
    s = re.sub("&nbsp;", " ", s)
    s = re.sub("&quot;", '"', s)
    s = re.sub("\s+", " ", s)
    s = s.strip(" ")
    s = unescape(s)
    return s

def get_contents(s):
    if 'http://' in s or 'https://' in s:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36'}
        try:
            o = requests.get(s, headers=headers).content
        except requests.exceptions.ConnectionError:
            o = ''
    else:
        o = open(s).read()
    return o

def unescape(text):
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)

main()
