"""Build Fantasy Handcuff Assist data from nflverse weekly CSVs.

usage:
  python3 scripts/build_data.py                 # downloads this season's nflverse files, writes data/backfields.js
  python3 scripts/build_data.py STATS INJ ROSTER OUT   # use local CSVs
"""
import csv, sys, json, os, datetime, tempfile, urllib.request
from collections import defaultdict

if len(sys.argv) >= 5:
    STATS, INJ, ROSTER, OUT = sys.argv[1:5]
else:
    today = datetime.date.today()
    yr = today.year if today.month >= 8 else today.year - 1
    base = 'https://github.com/nflverse/nflverse-data/releases/download'
    tmp = tempfile.mkdtemp()
    paths = []
    for rel in (f'stats_player/stats_player_week_{yr}.csv', f'injuries/injuries_{yr}.csv',
                f'weekly_rosters/roster_weekly_{yr}.csv'):
        dest = os.path.join(tmp, os.path.basename(rel))
        urllib.request.urlretrieve(f'{base}/{rel}', dest)
        paths.append(dest)
    STATS, INJ, ROSTER = paths
    OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'backfields.js')

ED_CUT = 69.0        # every-down: share >= this, season OR last 4
COMMITTEE_3RD = 15.0 # committee: 3rd back >= this share...
COMMITTEE_TOP = 50.0 # ...and no back >= this share
TREND_PTS = 5.0
MIN_GAMES = 2

TEAMS = {
 'ARI':'Arizona Cardinals','ATL':'Atlanta Falcons','BAL':'Baltimore Ravens','BUF':'Buffalo Bills',
 'CAR':'Carolina Panthers','CHI':'Chicago Bears','CIN':'Cincinnati Bengals','CLE':'Cleveland Browns',
 'DAL':'Dallas Cowboys','DEN':'Denver Broncos','DET':'Detroit Lions','GB':'Green Bay Packers',
 'HOU':'Houston Texans','IND':'Indianapolis Colts','JAX':'Jacksonville Jaguars','KC':'Kansas City Chiefs',
 'LA':'Los Angeles Rams','LAC':'Los Angeles Chargers','LV':'Las Vegas Raiders','MIA':'Miami Dolphins',
 'MIN':'Minnesota Vikings','NE':'New England Patriots','NO':'New Orleans Saints','NYG':'New York Giants',
 'NYJ':'New York Jets','PHI':'Philadelphia Eagles','PIT':'Pittsburgh Steelers','SEA':'Seattle Seahawks',
 'SF':'San Francisco 49ers','TB':'Tampa Bay Buccaneers','TEN':'Tennessee Titans','WAS':'Washington Commanders'}

num = lambda r, k: float(r.get(k) or 0)
rows = [r for r in csv.DictReader(open(STATS)) if r['season_type'] == 'REG']
season = rows[0]['season']
last_week = max(int(r['week']) for r in rows)

team_weeks = defaultdict(set)
rb = defaultdict(lambda: defaultdict(list))   # team -> week -> rows
for r in rows:
    team_weeks[r['team']].add(int(r['week']))
    if r['position'] == 'RB':
        rb[r['team']][int(r['week'])].append(r)

# ---- availability: IR/PUP from weekly rosters, game status + practice from injury reports
hist = defaultdict(dict)   # name -> week -> (status, abbr)
for r in csv.DictReader(open(ROSTER)):
    if r['position'] == 'RB':
        hist[r['full_name']][int(r['week'])] = (r['status'], r['status_description_abbr'])
ir_now = {}
for name, wk in hist.items():
    if wk.get(last_week, ('',))[0] != 'RES':
        continue
    start = last_week
    while wk.get(start - 1, ('',))[0] == 'RES':
        start -= 1
    ir_now[name] = (start, 'PUP' if wk[last_week][1] == 'R04' else 'IR')

inj_now = {}
for r in csv.DictReader(open(INJ)):
    if r['position'] == 'RB' and int(r['week']) == last_week:
        inj_now[r['full_name']] = dict(game=r['report_status'], injury=r['report_primary_injury'] or r['practice_primary_injury'],
                                       practice=r['practice_status'])

def status_for(name):
    if name in ir_now:
        w, kind = ir_now[name]
        if kind == 'PUP':
            return dict(code='PUP', label='PUP list', injury='')
        ret = w + 4
        return dict(code='IR', label='IR, eligible to return now' if ret <= last_week else f'IR, eligible Week {ret}', injury='')
    i = inj_now.get(name)
    if i and i['game'] in ('Out', 'Doubtful', 'Questionable'):
        return dict(code=i['game'][0], label=i['game'], injury=i['injury'])
    if i and i['practice'] and 'Full' not in i['practice'] and 'Not injury' not in (i['injury'] or ''):
        if 'Limited' in i['practice']:
            return dict(code='LP', label='Limited in practice', injury=i['injury'])
        return dict(code='DNP', label='Did not practice', injury=i['injury'])
    return None

# ---- per-player aggregation (season = games he played; last 4 = his games inside team's last 4)
players = {}
for team, weeks_rows in rb.items():
    weeks = sorted(team_weeks[team])
    l4 = set(weeks[-4:])
    team_opp = {w: sum(num(r, 'carries') + num(r, 'targets') for r in weeks_rows[w]) for w in weeks}
    team_car = {w: sum(num(r, 'carries') for r in weeks_rows[w]) for w in weeks}
    team_tgt = {w: sum(num(r, 'targets') for r in weeks_rows[w]) for w in weeks}
    for w in weeks:
        for r in weeks_rows[w]:
            c, t = num(r, 'carries'), num(r, 'targets')
            if c + t == 0:
                continue
            key = (r['player_id'], team)
            p = players.setdefault(key, defaultdict(float, name=r['player_display_name'], team=team, tg=len(weeks), weeks=[]))
            p['weeks'].append(w)
            p['g'] += 1
            for k, v in (('car', c), ('tgt', t), ('rec', num(r, 'receptions')), ('rushyd', num(r, 'rushing_yards')),
                         ('recyd', num(r, 'receiving_yards')), ('rushtd', num(r, 'rushing_tds')),
                         ('rectd', num(r, 'receiving_tds')), ('std', num(r, 'fantasy_points')),
                         ('ppr', num(r, 'fantasy_points_ppr'))):
                p[k] += v
            p['t_opp'] += team_opp[w]; p['t_car'] += team_car[w]; p['t_tgt'] += team_tgt[w]
            if w in l4:
                p['l4g'] += 1; p['l4opp'] += c + t; p['l4t_opp'] += team_opp[w]

pct = lambda a, b: round(100 * a / b, 1) if b else 0.0
plist = []
for (pid, team), p in players.items():
    g = p['g']
    half = (p['std'] + p['ppr']) / 2
    d = dict(id=pid, name=p['name'], team=team, g=int(g), tg=int(p['tg']),
             missed=int(p['tg'] - g),
             share=pct(p['car'] + p['tgt'], p['t_opp']),
             l4=pct(p['l4opp'], p['l4t_opp']) if p['l4g'] >= 1 else None,
             l4g=int(p['l4g']),
             car_sh=pct(p['car'], p['t_car']), tgt_sh=pct(p['tgt'], p['t_tgt']),
             opp=int(p['car'] + p['tgt']), car=int(p['car']), tgt=int(p['tgt']), rec=int(p['rec']),
             rushyd=int(p['rushyd']), recyd=int(p['recyd']),
             ypc=round(p['rushyd'] / p['car'], 1) if p['car'] else None,
             ypt=round(p['recyd'] / p['tgt'], 1) if p['tgt'] else None,
             rushtd=int(p['rushtd']), rectd=int(p['rectd']), td=int(p['rushtd'] + p['rectd']),
             pts={'ppr': round(p['ppr'], 1), 'half': round(half, 1), 'std': round(p['std'], 1)},
             ppg={'ppr': round(p['ppr'] / g, 1), 'half': round(half / g, 1), 'std': round(p['std'] / g, 1)},
             status=status_for(p['name']))
    d['trend'] = round(d['l4'] - d['share'], 1) if d['l4'] is not None and d['l4g'] >= 2 and g >= 3 else None
    plist.append(d)

# RB ranks by points per game (min 3 games), per format
for fmt in ('ppr', 'half', 'std'):
    ranked = sorted([p for p in plist if p['g'] >= 3], key=lambda p: -p['ppg'][fmt])
    for i, p in enumerate(ranked, 1):
        p.setdefault('rank', {})[fmt] = i
for p in plist:
    p.setdefault('rank', {})

teams = []
for team in sorted(rb):
    every = sorted([p for p in plist if p['team'] == team], key=lambda p: -p['opp'])
    # Backs on IR/PUP can't play, so they come off the depth chart and the next backs move up.
    is_out = lambda p: bool(p['status'] and p['status']['code'] in ('IR', 'PUP'))
    backs = [p for p in every if not is_out(p)]
    out = [p for p in every if is_out(p) and p['share'] >= 10][:3]
    top = backs[:3]
    q = [p for p in backs if p['g'] >= MIN_GAMES]
    ed = [p for p in q if p['share'] >= ED_CUT or (p['l4'] or 0) >= ED_CUT]
    shares = sorted((p['share'] for p in q), reverse=True)
    if ed:
        tier = 'every'
    elif len(shares) >= 3 and shares[2] >= COMMITTEE_3RD and shares[0] < COMMITTEE_TOP:
        tier = 'committee'
    else:
        tier = 'split'
    starter = None
    handcuff = None
    if ed:
        starter = max(ed, key=lambda p: p['share'])
        healthy = [p for p in backs if p is not starter]
        if healthy:
            handcuff = healthy[0]
            if handcuff not in top:
                top = [p for p in top if p is starter] + [handcuff] + [p for p in top if p not in (starter, handcuff)][:1]
    if starter:
        top = [starter] + [p for p in top if p is not starter]
    for p in every:
        p['role'] = ('starter' if p is starter else 'handcuff' if p is handcuff else None)
    teams.append(dict(abbr=team, name=TEAMS.get(team, team), tier=tier, games=len(team_weeks[team]),
                      starter=starter['id'] if starter else None,
                      handcuff=handcuff['id'] if handcuff else None,
                      backs=top, out=out))

payload = json.dumps(dict(season=int(season), through_week=last_week,
               partial_week=sorted(t for t, w in team_weeks.items() if last_week in w),
               rules=dict(every_down=ED_CUT, committee_third=COMMITTEE_3RD, committee_top=COMMITTEE_TOP, trend=TREND_PTS),
               teams=teams), separators=(',', ':'))
with open(OUT, 'w') as fh:
    fh.write(f'window.FHA_DATA = {payload};\n' if OUT.endswith('.js') else payload)

for t in teams:
    print(t['abbr'], t['tier'].upper(), ' | '.join(
        f"{p['name']} {p['share']}/{p['l4']} {p['ppg']['half']} r{p['rank'].get('half','-')}"
        f"{' [HC]' if p['role']=='handcuff' else ''}{' ['+p['status']['code']+']' if p['status'] else ''}" for p in t['backs'])
          + (f"  || OUT: {', '.join(p['name'] for p in t['out'])}" if t['out'] else ''))
