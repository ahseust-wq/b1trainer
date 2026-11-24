#!/usr/bin/env python3
"""Instagram bot for B1 Prüfungstrainer: publishes the prepared posts at random times,
answers comments, sends the Play Store link by private reply, and reveals quiz answers.

Uses the official Instagram API with Instagram Login (graph.instagram.com) and only the
Python standard library, so it runs on GitHub Actions or any computer with Python 3.9+.

  python3 bot/ig_bot.py run              # what the hourly job does: publish (if a slot is due), reveal, comments
  python3 bot/ig_bot.py plan             # show this and next week's random posting times
  python3 bot/ig_bot.py publish --post de-03-quiz-fuer   # publish one post now
  python3 bot/ig_bot.py comments --dry-run               # show what it would answer, change nothing
  python3 bot/ig_bot.py check            # validate posts and that every image URL is reachable
  python3 bot/ig_bot.py status

Secrets come from the environment (or --env-file): IG_ACCESS_TOKEN, IG_USER_ID, SCHEDULE_SALT.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replies as R  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = dt.timezone.utc


# ============================================================ helpers
def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
    tmp.replace(path)


def iso(t):
    return t.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_time(s):
    s = s.replace('Z', '+00:00')
    if len(s) >= 5 and s[-5] in '+-' and s[-3] != ':':   # Instagram gives +0000
        s = s[:-2] + ':' + s[-2:]
    return dt.datetime.fromisoformat(s).astimezone(UTC)


def load_env_file(path):
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Log:
    def __init__(self):
        self.lines = []

    def __call__(self, *a):
        msg = ' '.join(str(x) for x in a)
        self.lines.append(msg)
        print(msg, flush=True)


# ============================================================ API
def host_for(token):
    """Instagram-login tokens start with IG; Unified-login and Facebook-login tokens with EAA."""
    return 'https://graph.instagram.com' if (token or '').startswith('IG') else 'https://graph.facebook.com'


class ApiError(Exception):
    def __init__(self, status, body):
        self.status, self.body = status, body
        err = body.get('error', {}) if isinstance(body, dict) else {}
        self.code = err.get('code')
        super().__init__(f'HTTP {status}: {err.get("message") or body}')


class Api:
    """Thin client for graph.instagram.com. Every write goes through _call so dry-run can stop it."""

    def __init__(self, token, user_id, host='auto', version='v25.0', dry=False, log=print):
        host = host_for(token) if host == 'auto' else host
        self.token, self.uid, self.base, self.dry, self.log = token, user_id, f'{host}/{version}', dry, log
        # Unified login (new apps since late 2026) gives a system-user token for graph.facebook.com that
        # never expires; Instagram login (older apps) gives a 60-day token for graph.instagram.com.
        self.instagram_login = 'graph.instagram.com' in host

    def _call(self, method, path, params=None, body=None, base=None):
        params = dict(params or {})
        params['access_token'] = self.token
        url = (base or self.base) + '/' + path.lstrip('/') + '?' + urllib.parse.urlencode(params)
        data, headers = None, {}
        if body is not None:
            data, headers = json.dumps(body).encode(), {'Content-Type': 'application/json'}
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read() or b'{}')
            except urllib.error.HTTPError as e:
                try:
                    b = json.loads(e.read() or b'{}')
                except ValueError:
                    b = {}
                if e.code >= 500 and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise ApiError(e.code, b) from None
            except urllib.error.URLError:
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise

    def get(self, path, **params):
        return self._call('GET', path, params)

    def post(self, path, body):
        if self.dry:
            self.log('  [dry-run] POST', path, json.dumps(body, ensure_ascii=False)[:160])
            return {'id': 'DRYRUN'}
        return self._call('POST', path, body=body)

    def pages(self, path, limit=500, **params):
        """Follows paging.next; yields items."""
        out = self.get(path, **params)
        n = 0
        while True:
            for item in out.get('data', []):
                yield item
                n += 1
                if n >= limit:
                    return
            nxt = out.get('paging', {}).get('next')
            if not nxt:
                return
            with urllib.request.urlopen(nxt, timeout=60) as r:
                out = json.loads(r.read())

    # --- endpoints
    def me(self):
        """The account's own username (works with both kinds of token)."""
        return self.get(self.uid, fields='id,username')

    def publishing_quota(self):
        d = self.get(f'{self.uid}/content_publishing_limit', fields='config,quota_usage').get('data', [{}])[0]
        return d.get('quota_usage', 0), d.get('config', {}).get('quota_total', 50)

    def create_image(self, image_url, caption, alt_text):
        return self.post(f'{self.uid}/media', {'image_url': image_url, 'caption': caption, 'alt_text': alt_text})['id']

    def wait_ready(self, container, timeout=120):
        if self.dry:
            return
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.get(container, fields='status_code').get('status_code')
            if st == 'FINISHED':
                return
            if st in ('ERROR', 'EXPIRED'):
                raise RuntimeError(f'container {container}: {st}')
            time.sleep(4)
        raise RuntimeError(f'container {container} not ready after {timeout}s')

    def publish(self, container):
        return self.post(f'{self.uid}/media_publish', {'creation_id': container})['id']

    def permalink(self, media_id):
        if self.dry:
            return ''
        return self.get(media_id, fields='permalink').get('permalink', '')

    def recent_media(self, n):
        return list(self.pages(f'{self.uid}/media', limit=n, fields='id,caption,timestamp,permalink'))

    def comments(self, media_id):
        return list(self.pages(f'{media_id}/comments',
                               fields='id,text,timestamp,username,from,replies{id,username,text,timestamp}'))

    def reply(self, comment_id, text):
        return self.post(f'{comment_id}/replies', {'message': text})

    def comment(self, media_id, text):
        return self.post(f'{media_id}/comments', {'message': text})

    def private_reply(self, comment_id, text):
        return self.post(f'{self.uid}/messages', {'recipient': {'comment_id': comment_id}, 'message': {'text': text}})

    def refresh_token(self):
        return self._call('GET', 'refresh_access_token', {'grant_type': 'ig_refresh_token'},
                          base=self.base.rsplit('/', 1)[0])


# ============================================================ schedule
def week_key(d):
    y, w, _ = d.isocalendar()
    return f'{y}-W{w:02d}'


def week_slots(cfg, salt, any_day_in_week):
    """Random but reproducible posting times for one ISO week, as UTC datetimes.
    The same salt and week always give the same times, so every hourly run agrees on the plan."""
    tz = ZoneInfo(cfg['timezone'])
    monday = any_day_in_week - dt.timedelta(days=any_day_in_week.weekday())
    key = week_key(monday)
    rng = random.Random(hashlib.sha256(f'{salt}|{key}'.encode()).hexdigest())
    lo, hi = cfg['posts_per_week']
    n = rng.randint(lo, hi)
    windows = [tuple(int(x) for x in a.split(':')) + tuple(int(x) for x in b.split(':')) for a, b in cfg['windows']]
    gap = dt.timedelta(hours=cfg['min_hours_between_posts'])
    for _ in range(200):
        days = sorted(rng.sample(range(7), n))
        slots = []
        for d in days:
            h1, m1, h2, m2 = rng.choice(windows)
            start, end = h1 * 60 + m1, h2 * 60 + m2
            minute = rng.randint(start, end - 1)
            day = monday + dt.timedelta(days=d)
            local = dt.datetime(day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=tz)
            slots.append(local.astimezone(UTC))
        if all(b - a >= gap for a, b in zip(slots, slots[1:])):
            return key, slots
    return key, slots


def series_of(post):
    return post.get('series', 'main')


def tip_slot(cfg, salt, day):
    """One random time per day for the 'Tipp des Tages', never close to a main post that day."""
    t, tz = cfg['tips'], ZoneInfo(cfg['timezone'])
    rng = random.Random(hashlib.sha256(f'{salt}|tip|{day.isoformat()}'.encode()).hexdigest())
    main = [m for m in week_slots(cfg, salt, day)[1] if m.astimezone(tz).date() == day]
    gap = dt.timedelta(hours=t['min_gap_to_main_hours'])
    for _ in range(100):
        (a, b) = rng.choice(t['windows'])
        h1, m1 = (int(x) for x in a.split(':'))
        h2, m2 = (int(x) for x in b.split(':'))
        minute = rng.randint(h1 * 60 + m1, h2 * 60 + m2 - 1)
        slot = dt.datetime(day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=tz).astimezone(UTC)
        if all(abs(slot - m) >= gap for m in main):
            return slot
    return slot


def all_slots(cfg, salt, now):
    """(slot id, series, time) for every posting time from yesterday to today."""
    out = []
    for day in (now - dt.timedelta(days=7), now):
        out += [(iso(s), 'main', s) for s in week_slots(cfg, salt, day.date())[1]]
    if cfg.get('tips'):
        tz = ZoneInfo(cfg['timezone'])
        today = now.astimezone(tz).date()
        for day in (today - dt.timedelta(days=1), today):
            s = tip_slot(cfg, salt, day)
            out.append(('tip@' + iso(s), 'tip', s))
    return sorted(out, key=lambda x: x[2])


def due_slot(cfg, salt, state, now):
    """The earliest posting time that has passed, is not older than the tolerance and was not used yet.
    Returns (slot id, series) or None."""
    tol = dt.timedelta(hours=cfg['late_tolerance_hours'])
    used = set(state.setdefault('slots_done', []))
    for sid, series, s in all_slots(cfg, salt, now):
        if sid not in used and s <= now and now - s <= tol:
            return sid, series
    return None


# ============================================================ choosing the next post
def in_window(post, day):
    """Seasonal posts carry "window": [from, to] as MM-DD (every year) or YYYY-MM-DD (once)."""
    w = post.get('window')
    if not w:
        return True
    a, b = w
    if len(a) == 10:
        return a <= day.isoformat() <= b
    md = day.strftime('%m-%d')
    return a <= md <= b if a <= b else (md >= a or md <= b)      # a window like 12-18 .. 01-03


def window_days_left(post, day):
    for i in range(400):
        if not in_window(post, day + dt.timedelta(days=i + 1)):
            return i
    return 400


def next_post(posts, state, cfg, now, rng=random, series='main'):
    """posts: the posts of one series. Main posts come in random order with variety rules;
    tips come in their list order, one round after the other."""
    allpub = state.setdefault('published', [])
    pub = [p for p in allpub if p.get('series', 'main') == series]
    today = now.astimezone(ZoneInfo(cfg['timezone'])).date()
    first = cfg.get('first_post') if series == 'main' else None
    if not pub and first and any(p['id'] == first for p in posts):
        return next(p for p in posts if p['id'] == first)
    # seasonal posts first, while their window is open: the one whose window closes soonest
    shown = {}
    for p in pub:
        shown[p['post_id']] = max(shown.get(p['post_id'], ''), p['at'])
    season = [p for p in posts if p.get('window') and in_window(p, today)
              and not (p['id'] in shown and now - parse_time(shown[p['id']]) < dt.timedelta(days=300))]
    if season:
        return min(season, key=lambda p: (window_days_left(p, today), posts.index(p)))
    posts = [p for p in posts if not p.get('window')]
    ckey = 'cycle' if series == 'main' else 'cycle_' + series
    cycle = state.setdefault(ckey, 1)
    done = {p['post_id'] for p in pub if p.get('cycle') == cycle}
    todo = [p for p in posts if p['id'] not in done]
    if not todo:
        # every post went out once: start the next round, but only with posts not shown recently
        state[ckey] = cycle = cycle + 1
        todo = list(posts)
    last_seen = {}
    for p in pub:
        last_seen[p['post_id']] = max(last_seen.get(p['post_id'], ''), p['at'])
    days = cfg['repeat_after_days'] if series == 'main' else cfg[series + 's']['repeat_after_days']
    min_age = dt.timedelta(days=days)
    todo = [p for p in todo if p['id'] not in last_seen or now - parse_time(last_seen[p['id']]) >= min_age]
    if not todo:
        return None
    if series != 'main':
        return todo[0]
    by_id = {p['id']: p for p in posts}
    recent = [by_id[r['post_id']] for r in pub[-2:] if r['post_id'] in by_id]
    last = recent[-1] if recent else None
    left = {}
    for p in todo:
        left[p['kind']] = left.get(p['kind'], 0) + 1
    rest = sum(left.values())

    def allowed(p):
        if not last:
            return True
        if p['lang'] != 'de' and last['lang'] != 'de':          # never two non-German posts in a row
            return False
        if p['kind'] != last['kind']:
            return True
        # the same kind again only when it has at least as many posts left as all others together (quizzes),
        # and never three in a row
        run2 = len(recent) == 2 and recent[0]['kind'] == p['kind']
        return left[p['kind']] >= rest - left[p['kind']] and not run2

    pool = [p for p in todo if allowed(p)] or todo
    # kinds with many posts left are much more likely, so the end of a round is not one kind in a row
    return rng.choices(pool, weights=[left[p['kind']] ** 2 for p in pool])[0]


def image_url(cfg, post):
    return cfg['image_base_url'].rstrip('/') + '/' + post['image']


def play_url(cfg, lang, campaign):
    q = {'id': cfg['package'], 'hl': lang,
         'referrer': f'utm_source=instagram&utm_medium=social&utm_campaign={campaign}'}
    return 'https://play.google.com/store/apps/details?' + urllib.parse.urlencode(q)


# ============================================================ jobs
def job_publish(api, cfg, posts, state, now, log, force_id=None, salt=''):
    if force_id:
        post = next((p for p in posts if p['id'] == force_id), None)
        if not post:
            raise SystemExit(f'unknown post {force_id}')
        slot = None
    else:
        due = due_slot(cfg, salt, state, now)
        if not due:
            log('publish: no posting time due')
            return None
        slot, series = due
        pub = [p for p in state.get('published', []) if p.get('series', 'main') == series]
        min_gap = cfg['min_hours_between_posts'] if series == 'main' else cfg['tips']['min_hours_between']
        if pub and now - parse_time(pub[-1]['at']) < dt.timedelta(hours=min_gap):
            log('publish: last post too recent, skipping slot', slot)
            state['slots_done'].append(slot)
            return None
        post = next_post([p for p in posts if series_of(p) == series], state, cfg, now, series=series)
        if not post:
            log(f'publish: nothing to post in series {series} (all shown within repeat_after_days)')
            state['slots_done'].append(slot)
            return None
    used, total = api.publishing_quota() if not api.dry else (0, 50)
    if used >= total:
        log(f'publish: Instagram publishing limit reached ({used}/{total}), trying again next run')
        return None
    caption = post['caption']
    assert len(caption) <= 2200 and caption.count('#') <= 5, 'caption over Instagram limits'
    log(f'publish: {post["id"]} ({image_url(cfg, post)})')
    container = api.create_image(image_url(cfg, post), caption, post.get('alt_text', ''))
    api.wait_ready(container)
    media_id = api.publish(container)
    link = api.permalink(media_id)
    if api.dry:
        log('  [dry-run] not recorded')
        return post['id']
    ckey = 'cycle' if series_of(post) == 'main' else 'cycle_' + series_of(post)
    state.setdefault('published', []).append({'post_id': post['id'], 'media_id': media_id, 'at': iso(now),
                                              'series': series_of(post), 'cycle': state.get(ckey, 1), 'permalink': link})
    done = state.setdefault('slots_done', [])
    if slot:
        done.append(slot)
    state['slots_done'] = done[-120:]
    log(f'  published {media_id} {link}')
    return post['id']


def job_reveal(api, cfg, posts, state, now, log):
    by_id = {p['id']: p for p in posts}
    wait = dt.timedelta(hours=cfg['quiz_reveal_after_hours'])
    for rec in state.get('published', []):
        post = by_id.get(rec['post_id'])
        if not post or post['kind'] != 'quiz' or rec.get('revealed'):
            continue
        if now - parse_time(rec['at']) >= wait:
            text = post['reveal'].get(post['lang']) or next(iter(post['reveal'].values()))
            log(f'reveal: {post["id"]}')
            api.comment(rec['media_id'], text)
            if not api.dry:
                rec['revealed'] = iso(now)


def job_comments(api, cfg, posts, state, now, log, me, rng=random):
    """Answers new comments on our recent posts. Returns a list of comments that need a human."""
    c = cfg['comments']
    by_media = {rec['media_id']: rec for rec in state.get('published', [])}
    by_id = {p['id']: p for p in posts}
    handled = state.setdefault('handled', {})
    dm_users = state.setdefault('dm_users', {})
    dm_log = [t for t in state.get('dm_log', []) if now - parse_time(t) < dt.timedelta(days=1)]
    attention, actions = [], 0
    max_age = dt.timedelta(days=c['max_comment_age_days'])
    for m in api.recent_media(c['lookback_media']):
        rec = by_media.get(m['id'])
        post = by_id.get(rec['post_id']) if rec else None
        post_lang = post['lang'] if post else 'de'
        for cm in api.comments(m['id']):
            cid = cm['id']
            who = cm.get('username') or cm.get('from', {}).get('username', '')
            uid = cm.get('from', {}).get('id', who)
            if cid in handled or who.lower() == me.lower():
                continue
            if any((r.get('username') or '').lower() == me.lower() for r in cm.get('replies', {}).get('data', [])):
                handled[cid] = {'at': iso(now), 'action': 'already-answered'}
                continue
            if now - parse_time(cm['timestamp']) > max_age:
                handled[cid] = {'at': iso(now), 'action': 'too-old'}
                continue
            if actions >= c['max_replies_per_run']:
                log('comments: reply limit for this run reached, rest next run')
                break
            text = cm.get('text', '')
            lang = R.detect_lang(text, post_lang)
            intent, detail = R.classify(text, post)
            reply, dm, action = None, False, intent
            if intent in ('spam', 'empty'):
                pass
            elif intent in ('negative', 'question'):
                attention.append({'user': who, 'text': text, 'permalink': m.get('permalink', ''), 'why': intent})
            elif intent == 'quiz':
                right = detail == post['quiz']['answer']
                revealed = rec and rec.get('revealed')
                if right:
                    reply = rng.choice(R.QUIZ['right'])
                elif revealed:
                    k = 'abc'.index(post['quiz']['answer'])
                    reply = R.QUIZ['wrong_after'].format(letter=post['quiz']['answer'], word=post['design']['options'][k])
                else:
                    reply = rng.choice(R.QUIZ['wrong'])
                action = 'quiz-right' if right else 'quiz-wrong'
            elif intent == 'link':
                dm = True
            elif intent == 'faq':
                reply = R.pick('faq_' + detail, lang, rng)
                dm = c['dm_on_question'] and detail != 'ios'
                action = 'faq-' + detail
            elif intent == 'exam':
                reply = R.pick('luck', lang, rng)
            elif intent == 'generic' and rng.random() < c['reply_generic_rate']:
                reply = R.pick('thanks', lang, rng)
            # the private reply with the Play Store link: once per comment (Instagram rule), once per person per 30 days
            dm_ok = None
            if dm:
                recent = uid in dm_users and now - parse_time(dm_users[uid]) < dt.timedelta(days=30)
                if recent:
                    dm_ok = False
                    action += '+dm-recent'
                elif len(dm_log) >= c['max_dms_per_day']:
                    dm_ok = False
                    action += '+dm-daily-limit'
                else:
                    msg = R.T['dm_link'][lang].format(url=play_url(cfg, lang, rec['post_id'] if rec else 'instagram'))
                    try:
                        api.private_reply(cid, msg)
                        dm_ok = True
                        dm_users[uid] = iso(now)
                        dm_log.append(iso(now))
                        action += '+dm'
                    except ApiError as e:
                        dm_ok = False
                        action += f'+dm-failed({e.code})'
                        log(f'  private reply failed for {who}: {e}')
                if intent == 'link':
                    reply = R.pick('sent', lang, rng) if dm_ok else R.pick('bio', lang, rng)
                else:
                    reply += R.pick('suffix_dm' if dm_ok else 'suffix_bio', lang, rng)
            if reply:
                try:
                    api.reply(cid, reply)
                except ApiError as e:
                    log(f'  reply failed for {who}: {e}')
                    action += '+reply-failed'
            log(f'comment @{who} [{lang}] {text[:60]!r} -> {action}' + (f' | {reply[:70]!r}' if reply else ''))
            if reply or dm:
                actions += 1
            if not api.dry:
                handled[cid] = {'at': iso(now), 'action': action}
    # forget handled comments after 30 days (Instagram ignores older ones for private replies anyway)
    cutoff = now - dt.timedelta(days=30)
    state['handled'] = {k: v for k, v in handled.items() if parse_time(v['at']) > cutoff}
    state['dm_users'] = {k: v for k, v in dm_users.items() if parse_time(v) > cutoff}
    state['dm_log'] = dm_log
    if attention:
        state.setdefault('attention', []).extend(dict(a, at=iso(now)) for a in attention)
        state['attention'] = state['attention'][-50:]
    return attention


def job_refresh_token(api, state, now, out_file, log, every_days=7):
    if not api.instagram_login:
        return False          # Unified-login system-user tokens do not expire
    t = state.get('token_refreshed_at')
    if t and now - parse_time(t) < dt.timedelta(days=every_days):
        return False
    if api.dry:
        log('token: would refresh now')
        return False
    r = api.refresh_token()
    if not r.get('access_token'):
        log('token: refresh failed', r)
        return False
    pathlib.Path(out_file).write_text(r['access_token'])
    state['token_refreshed_at'] = iso(now)
    state['token_expires_at'] = iso(now + dt.timedelta(seconds=int(r.get('expires_in', 5184000))))
    log(f'token: refreshed, valid until {state["token_expires_at"]}')
    return True


# ============================================================ checks
def validate(posts, cfg, online=True, log=print):
    problems = []
    ids = set()
    for p in posts:
        if p['id'] in ids:
            problems.append(f'{p["id"]}: duplicate id')
        ids.add(p['id'])
        if len(p['caption']) > 2200:
            problems.append(f'{p["id"]}: caption {len(p["caption"])} > 2200 characters')
        if p['caption'].count('#') > 5:
            problems.append(f'{p["id"]}: more than 5 hashtags')
        if len(p.get('alt_text', '')) > 1000:
            problems.append(f'{p["id"]}: alt text too long')
        if p['lang'] not in R.LANGS:
            problems.append(f'{p["id"]}: unknown language')
        if p['kind'] == 'quiz' and (p['quiz']['answer'] not in 'abc' or not p.get('reveal')):
            problems.append(f'{p["id"]}: quiz without answer or reveal text')
        local = ROOT / 'out' / p['image']
        if not local.exists():
            problems.append(f'{p["id"]}: image {local} missing (run design/render.py)')
        if online:
            url = image_url(cfg, p)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=20) as r:
                    if r.status != 200 or 'jpeg' not in r.headers.get('Content-Type', ''):
                        problems.append(f'{p["id"]}: {url} gives {r.status} {r.headers.get("Content-Type")}')
            except Exception as e:  # noqa: BLE001
                problems.append(f'{p["id"]}: {url} not reachable ({e})')
    missing = R.check_texts()
    if missing:
        problems.append(f'missing reply texts: {missing}')
    return problems


def whoami(token, cfg):
    """Shows which kind of token this is and which Instagram account IDs it can use (for IG_USER_ID)."""
    if not token:
        raise SystemExit('set IG_ACCESS_TOKEN first')
    token = token.strip()
    host = host_for(token) if cfg['api_host'] == 'auto' else cfg['api_host']
    print('token kind:', 'Instagram login (graph.instagram.com, 60 days)' if 'instagram' in host
          else 'Unified or Facebook login (graph.facebook.com)', '| length', len(token))
    api = Api(token, 'me', host, cfg['api_version'])
    tries = [('me', {'fields': 'user_id,username'})] if 'instagram' in host else [
        ('me', {'fields': 'id,name'}),
        ('me/assigned_instagram_accounts', {'fields': 'id,username'}),
        ('me/accounts', {'fields': 'name,instagram_business_account{id,username}'})]
    for path, params in tries:
        try:
            print(path, '->', json.dumps(api.get(path, **params), ensure_ascii=False))
        except (ApiError, OSError) as e:
            print(path, '->', e)
    print('IG_USER_ID is the Instagram account id: "user_id" (Instagram login) or the "id" next to your username.')
    return 0


# ============================================================ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['run', 'plan', 'publish', 'comments', 'reveal', 'refresh-token', 'check', 'status', 'whoami'])
    ap.add_argument('--post', help='publish this post id now (publish only)')
    ap.add_argument('--dry-run', action='store_true', help='read from Instagram but change nothing')
    ap.add_argument('--config', default=str(ROOT / 'bot' / 'config.json'))
    ap.add_argument('--posts', default=str(ROOT / 'content' / 'posts.json'))
    ap.add_argument('--state', default=str(ROOT / 'state' / 'state.json'))
    ap.add_argument('--env-file')
    ap.add_argument('--token-out', default=os.environ.get('TOKEN_OUT', ''), help='file for a refreshed token')
    ap.add_argument('--offline', action='store_true', help='check: skip the image URL test')
    ap.add_argument('--now', help='pretend it is this UTC time (testing)')
    a = ap.parse_args(argv)
    if a.env_file:
        load_env_file(a.env_file)
    cfg = load_json(a.config, None)
    posts = load_json(a.posts, None)['posts']
    state = load_json(a.state, {})
    now = parse_time(a.now) if a.now else dt.datetime.now(UTC).replace(microsecond=0)
    salt = os.environ.get('SCHEDULE_SALT', 'change-me')
    log = Log()

    if a.command == 'plan':
        tz = ZoneInfo(cfg['timezone'])
        for day in (now.date(), now.date() + dt.timedelta(days=7)):
            key, slots = week_slots(cfg, salt, day)
            print(key + ': ' + ', '.join(s.astimezone(tz).strftime('%a %d.%m. %H:%M') for s in slots))
        if cfg.get('tips'):
            today = now.astimezone(tz).date()
            print('Tipp des Tages: ' + ', '.join(tip_slot(cfg, salt, today + dt.timedelta(days=i)).astimezone(tz).strftime('%a %H:%M') for i in range(7)))
        return 0
    if a.command == 'check':
        problems = validate(posts, cfg, online=not a.offline)
        for p in problems:
            print('PROBLEM', p)
        print(f'{len(posts)} posts checked, {len(problems)} problems')
        return 1 if problems else 0
    if a.command == 'status':
        print(f'cycle {state.get("cycle", 1)}, {len(state.get("published", []))} posts published')
        for r in state.get('published', [])[-10:]:
            print(' ', r['at'], r['post_id'], r.get('permalink', ''))
        if state.get('token_expires_at'):
            print('token valid until', state['token_expires_at'])
        for x in state.get('attention', [])[-10:]:
            print('  needs you:', x['at'], '@' + x['user'], repr(x['text'][:80]), x['permalink'])
        return 0

    token, uid = os.environ.get('IG_ACCESS_TOKEN'), os.environ.get('IG_USER_ID') or cfg.get('ig_user_id')
    if a.command == 'whoami':
        return whoami(token, cfg)
    if not token or not uid:
        raise SystemExit('IG_ACCESS_TOKEN and IG_USER_ID must be set (see README)')
    api = Api(token, uid, cfg['api_host'], cfg['api_version'], dry=a.dry_run, log=log)
    me = os.environ.get('IG_USERNAME') or api.me().get('username', '')
    status = 0
    try:
        if a.command in ('run', 'publish'):
            job_publish(api, cfg, posts, state, now, log, force_id=a.post, salt=salt)
        if a.command in ('run', 'reveal'):
            job_reveal(api, cfg, posts, state, now, log)
        if a.command in ('run', 'comments'):
            need = job_comments(api, cfg, posts, state, now, log, me)
            for x in need:
                log(f'NEEDS YOU: @{x["user"]}: {x["text"]!r} ({x["why"]}) {x["permalink"]}')
        if a.command == 'refresh-token' and not a.token_out:
            raise SystemExit('refresh-token needs --token-out FILE')
        if a.command in ('run', 'refresh-token') and a.token_out:
            job_refresh_token(api, state, now, a.token_out, log, every_days=0 if a.command == 'refresh-token' else 7)
    except ApiError as e:
        log('ERROR', e)
        status = 1
        if e.code == 190:
            log('The access token is wrong, expired or revoked: create a new one (README, step 4).')
    finally:
        if not a.dry_run:
            save_json(a.state, state)
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a', encoding='utf-8') as f:
                f.write('```\n' + '\n'.join(log.lines) + '\n```\n')
    return status


if __name__ == '__main__':
    sys.exit(main())
