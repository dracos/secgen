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
import urllib
import htmlentitydefs
from datetime import datetime, timedelta
from time import strptime, sleep
from BeautifulSoup import BeautifulSoup
import tweepy
from config import *

localfile = '/guest/matthew/data/secgen-schedule'

REGEX_TIME = re.compile('((\d+)(?:(?::|\.)\s*(\d+)|\s+(a\.?m\.?|p\.?m\.?|noon))+\.?)')

def main():
    p = argparse.ArgumentParser(description="UN Secretary-General > Twitter v1.0")
    choices = [ 'fetch', 'twitter', 'test' ]
    p.add_argument('action', choices=choices,
            help='Action to perform; one of %s' % ', '.join(choices) )
    options = p.parse_args()

    if options.action == 'fetch':
        if fetch():
            test()
    elif options.action == 'twitter':
        now = datetime.today()
        for time, event in parse():
            if now>=time and now<time+timedelta(minutes=5):
                twitter(event)
    elif options.action == 'test':
        test()
    else:
        p.print_help()

def test():
    for time, event in parse(warn=1):
        print time, event.encode('utf-8')

def fetch():
    new = get_contents('http://www.un.org/sg/sg_schedule.asp')
    current = ''
    try:
        current = get_contents(localfile)
    except:
        pass
    if current != new and not re.search('Not Found|Service Temporarily Unavailable|HTTP Error 50[17]|SQLState(?i)', new):
        f = open(localfile, 'w')
        f.write(new)
        f.close()
        try:
            os.remove('%s-override' % localfile)
        except:
            pass
        print "New schedule downloaded"
        return True
    return False

def parse(warn=0):
    try:
        d = get_contents("%s-override" % localfile)
    except:
        d = get_contents(localfile)
    if re.search('Proxy Error', d) or re.search('website is undergoing urgent maintenance', d):
        if warn:
            print 'Have downloaded a proxy error...'
        return []
    soup = BeautifulSoup(d, smartQuotesTo=None)
    table = soup.find('div', id='content')
    events = []
    pastnoon = False
    date = strptime(table.find('b').renderContents(), '%A, %d %B %Y')
    for row in table('tr'):
        row = parsecell(row.renderContents().decode('utf-8'))
        m = REGEX_TIME.match(row)
        if not m:
            if row[0:2] == '- ':
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

    if len(s)>140:
        wrapped = textwrap.wrap(s, 139)
    else:
        wrapped = [ s ]
    resp = ''
    first = True
    for line in wrapped:
        if resp:
            sleep(5)
        if first and len(wrapped)>1:
            line = u"%s\u2026" % line
        if not first:
            line = u"\u2026%s" % line
        resp += api.update_status(line).text
        first = False
    return resp

def parsetime(time, date, pastnoon):
    m = REGEX_TIME.search(time)
    if m:
        (dummy, hour, min, pm) = m.groups()
        if min == None:
            min = 0
    elif time == 'noon':
        hour = 12
        min = 0
        pm = 'noon'
    hour = int(hour)
    min = int(min)
    if not pm and pastnoon:
        hour += 12
    if pm in ('pm', 'p.m.') and hour != 12:
        hour += 12
    if pm in ('am', 'a.m.') and hour == 12:
        hour -= 12
    if pm in ('pm', 'p.m.', 'noon'):
        pastnoon = True
    d = datetime(date.tm_year, date.tm_mon, date.tm_mday, hour, min)
    d += timedelta(hours=5) # Assume we're in New York, and BST is same (which it isn't)
    return d, pastnoon

def prettify(s):
    if re.match('Addressing|Meeting (with|on)|Visiting|Visit to|Trilateral Meeting', s) and not re.search('Secretary-General (will|to) make remarks', s):
        return s
    if re.match('Joint press encounter by the Secretary-General with: ', s):
        return re.sub('Joint press encounter by the Secretary-General with: ', 'Joint press encounter with ', s)
    if re.match('Joint Declaration on (.*?) by the Secretary-General and ', s):
        return re.sub('Joint (.*?) by the Secretary-General and ', r'Joint \1 with ', s)
    if re.match('Secretary-General[^a-zA-Z]*(to|will) address ', s):
        return re.sub('Secretary-General[^a-zA-Z]*(to|will) address ', 'Addressing ', s)
    if re.match('Secretary-General to make ', s):
        return re.sub('Secretary-General to make ', 'Making ', re.sub(r'\bhis\b', 'my', s))
    if re.match('Secretary-General to attend ', s):
        return re.sub('Secretary-General to attend ', 'Attending ', s)
    if re.match('Secretary-General to brief ', s):
        return re.sub('Secretary-General to brief ', 'Briefing ', s)
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
    if re.match('Remarks by the Secretary-General |SG remarks at|Secretary(-| )General (to give )?remarks at', s):
        return re.sub('Remarks by the Secretary-General |SG remarks |Secretary(-| )General (to give )?remarks ', 'Making remarks ', s)
    if re.search(' (?:.\200\223 |- |\[|{|\()Secretary-General (?:to|will) make remarks(\]|}|\))?\.?$', s):
        new = 'Making remarks at '
        s = re.sub('^Addressing ', '', s)
        if not re.match('The (?i)', s): new += 'the '
        return re.sub('^(.*) (?:.\200\223 |- |\[|{|\()Secretary-General (?:to|will) make remarks(\]|}|\))?', new + r'\1', s)
    if re.match('\[Remarks at\] ', s):
        return re.sub('\[Remarks at\] ', 'Making remarks at ', s)
    if re.search('Presentation of credential(?i)', s) or re.match('Remarks at', s) or re.match('Election of', s) or re.match('Swearing[ -]in Ceremony', s):
        pass
    elif re.search('(?<!on )Youth$|^Group of Friends|^Leaders|^Chairmen|^Permanent Representatives?|^Executive Secretaries|Board members|Contact Group|Envoys|Team$|^Honou?rable|Interns|Order|Board of Trustees|Journalists|Committee$', s) and not re.search('(concert|luncheon|breakfast|event)(?i)', s):
        s = 'Meeting the %s' % s
    elif re.match('- Mr|His Royal Highness|President|Association of|Vuk|Queen|Prince|Major-General|His Excellency|His Eminence|His Holiness|His Majesty|Ambassador|H\.?R\.?H|H\. ?M\.|H\. ?H\.|H\.? ?E\.?|S\. ?E\.|Rev\.|Sir|General (?!Assembly)|H\.S\.H|Mr\.|Mrs\.|Prof\.|Dr\.?|Justice|Professor|Ms\.?|Amb\.?|Mayor|Messrs\.|Senator|(The )?R(igh)?t\.? Hon(ou?rable)?\.?|The Hon\.|Hon\.|U\.S\. House|U\.S\. Senator|US Congressman|Judge|Archbishop|The Honou?rable|Rabbi|Lt\.|Major General|Excelent|Metropolitan|Psy|Thura|Lang Lang|Bahey', s) and not re.search('luncheon(?i)', s):
        s = re.sub('Amb\.', 'Ambassador', s)
        s = re.sub('^Amb ', 'Ambassador ', s)
        s = 'Meeting %s' % s
    elif re.search('Delegation|Members', s) and not re.search('(Group Meeting|concert|luncheon|breakfast)(?i)', s):
        s = 'Meeting the %s' % s
    elif re.search('Secretary-General of the League|Senior Adviser|Special Adviser|Permanent Representative|Minister of|Secretary of State for|Administrator|CEO|National Adviser|Ambassador|students|Students', s) and not re.search('(concert|luncheon|breakfast|hosted by)(?i)', s):
        s = 'Meeting %s' % s
    elif re.match('The ', s):
        s = re.sub('^The ', 'Attending the ', s)
    else:
        s = 'Attending the %s' % s
    return s

def parsecell(s, d=False):
    s = re.sub('\xc2\xa0', ' ', s)
    if d:
        s = re.sub("<br />", ", ", s)
        s = re.sub("</p>", " ", s)
    s = re.sub("<[^>]*>", "", s)
    s = re.sub("&nbsp;", " ", s)
    s = re.sub("&quot;", '"', s)
    s = re.sub("\s+", " ", s)
    s = s.strip(" ;")
    s = unescape(s)
    return s

def get_contents(s):
    if 'http://' in s:
        f = urllib.urlopen(s)
    else:
        f = open(s)
    o = f.read()
    f.close()
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
