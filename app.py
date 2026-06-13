#!/usr/bin/env python3
"""
Stargate Capex — Flask API
Runs on $PORT (Render) or 5052 (local)
SEO: robots.txt, sitemap.xml, llms.txt, server-rendered /leads page
"""
import os, sqlite3, json
from flask import abort
from datetime import datetime
from flask import Response
from flask import Flask, jsonify, request, send_from_directory, render_template

app = Flask(__name__, static_folder='portal', static_url_path='', template_folder='templates')

# Relative path works both locally and on Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, 'leads', 'stargate_capex.db')
PORT = int(os.environ.get('PORT', 5052))

@app.after_request
def add_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

DEFAULT_STARGATE_FAQS = [
    {
        "question": "What is the Project Stargate CapEx Terminal?",
        "answer": "The Stargate CapEx Terminal is a company directory and business intelligence platform indexing contractors, fabricators, and power suppliers active in the $500B Project Stargate AI infrastructure corridor."
    },
    {
        "question": "How are companies scored on the terminal?",
        "answer": "Companies are scored based on their proximity to active Stargate computing nodes (Abilene TX, Columbus OH, Albuquerque NM) and the maturity of their UCC-1 equipment financing statements."
    },
    {
        "question": "Where is the UCC filing database sourced from?",
        "answer": "Our database compiles public filings from state Secretary of State offices across GA, CO, CT, CA, TX, MT, ID, NY, MA, NJ, AZ, FL, WY, IL, UT, OK."
    }
]

@app.route('/')
def index():
    """Serve homepage — inject top companies as SSR for Google indexing."""
    try:
        conn = get_db()
        rows = conn.execute(
            '''SELECT company_name, city, state, secured_party, lien_type,
                      propensity_score, nearest_node, days_to_lapse, filing_date
               FROM active_stargate_leads
               ORDER BY propensity_score DESC LIMIT 25'''
        ).fetchall()
        conn.close()
        activity = [dict(r) for r in rows]
    except Exception:
        activity = []
    return render_template('index.html', activity=activity, faq_data=DEFAULT_STARGATE_FAQS)

@app.route('/api/stats')
def api_stats():
    conn = get_db()
    r = conn.execute('''SELECT
        COUNT(*) total,
        SUM(CASE WHEN propensity_score>=85 THEN 1 ELSE 0 END) priority,
        SUM(CASE WHEN propensity_score>=65 AND propensity_score<85 THEN 1 ELSE 0 END) hot,
        SUM(CASE WHEN propensity_score>=40 AND propensity_score<65 THEN 1 ELSE 0 END) monitor,
        SUM(CASE WHEN lien_type="equipment" THEN 1 ELSE 0 END) equipment,
        SUM(CASE WHEN lien_type="blanket"   THEN 1 ELSE 0 END) mca
        FROM active_stargate_leads''').fetchone()
    conn.close()
    return jsonify(dict(r) if r else {})

@app.route('/api/leads')
def api_leads():
    min_score = float(request.args.get('min_score', 0))
    state     = request.args.get('state', '')
    node      = request.args.get('node', '')
    tier      = request.args.get('tier', '')
    lien_type = request.args.get('lien_type', '')
    search    = request.args.get('search', '')
    sort_col  = request.args.get('sort', 'propensity_score')
    sort_dir  = request.args.get('dir', 'desc')
    limit     = min(int(request.args.get('limit', 500)), 2000)

    allowed_cols = {'propensity_score','days_to_lapse','filing_age_months','node_dist_km','company_name'}
    if sort_col not in allowed_cols: sort_col = 'propensity_score'
    if sort_dir not in ('asc','desc'): sort_dir = 'desc'

    where = ['propensity_score >= ?']
    params = [min_score]

    if state:
        where.append('state = ?'); params.append(state.upper())
    if node:
        where.append('nearest_node_id = ?'); params.append(node)
    if lien_type:
        where.append('lien_type = ?'); params.append(lien_type)
    if tier == 'priority':
        where.append('propensity_score >= 85')
    elif tier == 'hot':
        where.append('propensity_score >= 65 AND propensity_score < 85')
    elif tier == 'monitor':
        where.append('propensity_score >= 40 AND propensity_score < 65')
    elif tier == 'low':
        where.append('propensity_score < 40')
    if search:
        where.append('LOWER(company_name) LIKE ?')
        params.append(f'%{search.lower()}%')

    sql = f'''SELECT id, file_id, company_name, city, state, filing_date, lapse_date,
                     days_to_lapse, secured_party, collateral, lien_type,
                     nearest_node, nearest_node_id, node_dist_km, propensity_score,
                     stargate_match, source_state, source_db, phone, email,
                     filing_age_months
              FROM active_stargate_leads
              WHERE {" AND ".join(where)}
              ORDER BY {sort_col} {sort_dir}
              LIMIT ?'''
    params.append(limit)

    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        try:
            d['stargate_match'] = json.loads(d['stargate_match'] or '{}')
        except:
            d['stargate_match'] = {}
        results.append(d)

    return jsonify(results)

@app.route('/api/nodes')
def api_nodes():
    conn = get_db()
    rows = conn.execute('''SELECT nearest_node, nearest_node_id, COUNT(*) cnt
                           FROM active_stargate_leads
                           GROUP BY nearest_node_id
                           ORDER BY cnt DESC''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/states')
def api_states():
    conn = get_db()
    rows = conn.execute('''SELECT state, COUNT(*) cnt
                           FROM active_stargate_leads
                           WHERE state IS NOT NULL AND state != ""
                           GROUP BY state ORDER BY cnt DESC''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── SEO ROUTES ──────────────────────────────────────────────────────────────────────────

@app.route('/robots.txt')
def robots():
    txt = """User-agent: *
Allow: /

# Google
User-agent: Googlebot
Allow: /

User-agent: Googlebot-Image
Allow: /

User-agent: Google-Extended
Allow: /

# Bing
User-agent: Bingbot
Allow: /

# OpenAI
User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: OAI-SearchBot
Allow: /

# Anthropic / Claude
User-agent: anthropic-ai
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Claude-Web
Allow: /

# Perplexity
User-agent: PerplexityBot
Allow: /

# Meta
User-agent: Meta-ExternalAgent
Allow: /

User-agent: FacebookBot
Allow: /

# Apple
User-agent: Applebot
Allow: /

# You.com
User-agent: YouBot
Allow: /

# Cohere
User-agent: cohere-ai
Allow: /

# Common crawl (feeds AI training)
User-agent: CCBot
Allow: /

# DuckDuckGo
User-agent: DuckAssistant
Allow: /

# Brave
User-agent: Brave-Search
Allow: /

Sitemap: https://stargatecapex.com/sitemap.xml
Sitemap: https://stargatecapex.com/sitemap-static.xml
"""
    resp = Response(txt, mimetype='text/plain')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/sitemap.xml')
def sitemap():
    """Sitemap index — lists all child company sitemaps."""
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM active_stargate_leads').fetchone()[0]
    conn.close()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    import math
    per_page = 5000
    num_children = math.ceil(total / per_page)

    child_refs = ''.join(
        f"""
  <sitemap>
    <loc>https://stargatecapex.com/sitemap-child-{i+1}.xml</loc>
    <lastmod>{today}</lastmod>
  </sitemap>"""
        for i in range(num_children)
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{child_refs}
</sitemapindex>"""
    return Response(xml, mimetype='application/xml')


@app.route('/sitemap-static.xml')
def sitemap_static():
    """Static pages sitemap."""
    today = datetime.utcnow().strftime('%Y-%m-%d')
    
    state_urls = ""
    for slug in STATE_MAP.keys():
        state_urls += f"""  <url>
    <loc>https://stargatecapex.com/companies/state/{slug}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>\n"""

    node_urls = ""
    for slug in NODE_MAP.keys():
        node_urls += f"""  <url>
    <loc>https://stargatecapex.com/companies/node/{slug}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
    <lastmod>{today}</lastmod>
  </url>\n"""

    # Fetch top cities from DB dynamically
    conn = get_db()
    city_rows = conn.execute("SELECT city FROM active_stargate_leads WHERE city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC LIMIT 200").fetchall()
    conn.close()
    
    dynamic_city_slugs = []
    for r in city_rows:
        city_raw = r[0].strip()
        if city_raw.isdigit() or len(city_raw) < 2:
            continue
        slug = city_raw.lower().replace(' ', '-')
        if slug not in dynamic_city_slugs:
            dynamic_city_slugs.append(slug)
            if len(dynamic_city_slugs) >= 100:
                break

    all_city_slugs = list(CITY_MAP.keys())
    for c_slug in dynamic_city_slugs:
        if c_slug not in all_city_slugs:
            all_city_slugs.append(c_slug)

    city_urls = ""
    for slug in all_city_slugs:
        city_urls += f"""  <url>
    <loc>https://stargatecapex.com/companies/city/{slug}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
    <lastmod>{today}</lastmod>
  </url>\n"""

    blog_urls = ""
    for post in STARGATE_BLOG_POSTS:
        blog_urls += f"""  <url>
    <loc>https://stargatecapex.com/blog/{post['slug']}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
    <lastmod>{today}</lastmod>
  </url>\n"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://stargatecapex.com/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/leads</loc>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
    <lastmod>{today}</lastmod>
  </url>
  <!-- State landing pages -->
{state_urls}  <!-- Node landing pages -->
{node_urls}  <!-- City landing pages -->
{city_urls}  <!-- Blog index and posts -->
  <url>
    <loc>https://stargatecapex.com/blog</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>
{blog_urls}</urlset>"""
    return Response(xml, mimetype='application/xml')


@app.route('/sitemap-child-<int:page>.xml')
def sitemap_child(page):
    """Paginated company sitemaps — 5000 per page covering all 16k+ companies."""
    per_page = 5000
    offset = (page - 1) * per_page
    conn = get_db()
    rows = conn.execute(
        'SELECT company_name, city, state FROM active_stargate_leads ORDER BY propensity_score DESC LIMIT ? OFFSET ?',
        (per_page, offset)
    ).fetchall()
    conn.close()

    if not rows:
        from flask import abort
        abort(404)

    today = datetime.utcnow().strftime('%Y-%m-%d')
    from urllib.parse import quote_plus
    items = ''
    for r in rows:
        name = str(r['company_name'] or '')
        search_q = quote_plus(name)
        items += f"""
  <url>
    <loc>https://stargatecapex.com/leads?search={search_q}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
    <lastmod>{today}</lastmod>
  </url>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}
</urlset>"""
    return Response(xml, mimetype='application/xml')


@app.route('/llms.txt')
def llms_txt():
    conn = get_db()
    stats = conn.execute('''SELECT COUNT(*) total,
        SUM(CASE WHEN propensity_score>=85 THEN 1 ELSE 0 END) priority,
        SUM(CASE WHEN lien_type="equipment" THEN 1 ELSE 0 END) equipment,
        SUM(CASE WHEN lien_type="blanket" THEN 1 ELSE 0 END) mca
        FROM active_stargate_leads''').fetchone()
    top = conn.execute(
        "SELECT company_name, city, state, nearest_node, propensity_score, lien_type FROM active_stargate_leads ORDER BY propensity_score DESC LIMIT 20"
    ).fetchall()
    conn.close()

    top_list = '\n'.join(
        f'- {r["company_name"]} ({r["city"]}, {r["state"]}) — Score {r["propensity_score"]} — Nearest: {r["nearest_node"]}'
        for r in top
    )

    txt = f"""# Stargate Capex

> The definitive UCC-1 equipment financing and MCA lead intelligence terminal for the $500 billion Project Stargate AI data center buildout corridor.

Stargate Capex tracks contractors, fabricators, power vendors, and equipment operators whose UCC-1 financing is maturing now — companies actively in the market for new capital. Leads are scored and ranked by proximity to active Stargate construction nodes across the United States.

## What This Site Does

Stargate Capex indexes public UCC-1 filings (Uniform Commercial Code financing statements) from state Secretary of State databases and cross-references them against companies operating near Project Stargate AI infrastructure sites. It provides a scored, filtered terminal for B2B equipment financing and MCA (merchant cash advance) lead generation.

## Database Stats (Live)

- Total Stargate-relevant leads: {stats['total']:,}
- Priority leads (score 85+): {stats['priority']:,}
- Equipment liens: {stats['equipment']:,}
- MCA / Blanket liens: {stats['mca']:,}

## Project Stargate Nodes Covered

- **Abilene Campus** — Abilene, Texas (Live — 200MW, OpenAI/Oracle flagship)
- **The Barn** — Saline, Michigan ($16B, Related Digital / Blackstone)
- **Lighthouse** — Port Washington, Wisconsin (2028, ~1GW, Vantage Data Centers)
- **Columbus Campus** — Columbus, Ohio (Planned)
- **ABQ Campus** — Albuquerque, New Mexico (Planned)

## Lead Categories

Leads are matched against these Stargate supply chain keyword categories:
- Construction & Civil (contractors, excavating, concrete, structural steel, grading)
- Power & Electrical (electricians, substations, generators, transformers, UPS, solar)
- Mechanical & Cooling (HVAC, chillers, refrigeration, air handling, plumbing)
- Fiber & IT Infrastructure (fiber, cabling, networking, telecommunications, data center)
- Heavy Equipment & Logistics (cranes, rigging, flatbed trucking, excavators)
- Manufacturing & Fabrication (steel fab, metal, welding, machining)

## Top Priority Leads (Sample)

{top_list}

## API Endpoints

- GET /api/stats — Returns total lead counts by tier and type
- GET /api/leads — Returns filtered leads (params: min_score, tier, node, state, lien_type, search)
- GET /api/nodes — Returns lead counts by Stargate node
- GET /api/states — Returns lead counts by state
- GET /leads — Server-rendered HTML version of lead database

## Data Sources

Public UCC-1 filings from state Secretary of State offices (GA, CO, CA, CT, ID, MT, TX, MI, WI, OH, NM). Data is for informational and lead generation purposes only.

## Contact

site: https://stargatecapex.com
"""
    return Response(txt, mimetype='text/plain')


@app.route('/llms-full.txt')
def llms_full_txt():
    """Extended llms.txt — full top 100 companies for AI crawlers."""
    conn = get_db()
    stats = conn.execute('''SELECT COUNT(*) total,
        SUM(CASE WHEN propensity_score>=85 THEN 1 ELSE 0 END) priority,
        SUM(CASE WHEN lien_type="equipment" THEN 1 ELSE 0 END) equipment,
        SUM(CASE WHEN lien_type="blanket" THEN 1 ELSE 0 END) mca
        FROM active_stargate_leads''').fetchone()
    top = conn.execute(
        """SELECT company_name, city, state, nearest_node,
                  propensity_score, lien_type, secured_party, days_to_lapse
           FROM active_stargate_leads ORDER BY propensity_score DESC LIMIT 100"""
    ).fetchall()
    conn.close()

    top_list = '\n'.join(
        f'- {r["company_name"]} ({r["city"]}, {r["state"]}) | '
        f'Type: {r["lien_type"].title()} | Lender: {r["secured_party"] or "N/A"} | '
        f'Score: {r["propensity_score"]} | Node: {r["nearest_node"]} | '
        f'Days to Lapse: {r["days_to_lapse"] or "N/A"}'
        for r in top
    )

    txt = f"""# Stargate Capex — Full Company Index (llms-full.txt)

> Extended AI retrieval index for the $500B Project Stargate UCC-1 company database.

## Database Summary

- Total companies indexed: {stats['total']:,}
- Priority tier (score 85+): {stats['priority']:,}
- Equipment liens: {stats['equipment']:,}
- MCA / Blanket liens: {stats['mca']:,}

## Active Stargate Nodes

- Abilene Campus — Abilene, Texas
- Columbus Campus — Columbus, Ohio
- ABQ Campus — Albuquerque, New Mexico

## Top 100 Companies by Propensity Score

{top_list}

## Browse Full Directory

- All companies: https://stargatecapex.com/leads
- Priority only: https://stargatecapex.com/leads?tier=priority
- Abilene TX: https://stargatecapex.com/leads?node=abilene
- Columbus OH: https://stargatecapex.com/leads?node=columbus
- Albuquerque NM: https://stargatecapex.com/leads?node=albuquerque

site: https://stargatecapex.com
"""
    return Response(txt, mimetype='text/plain')


# ── PROGRAMMATIC SEO: STATE + NODE LANDING PAGES ───────────────────────────────

STATE_MAP = {
    'alabama':       ('AL',  'ALABAMA'),
    'alaska':        ('AK',  'ALASKA'),
    'arizona':       ('AZ',  'ARIZONA'),
    'arkansas':      ('AR',  'ARKANSAS'),
    'california':    ('CA',  'CALIFORNIA'),
    'colorado':      ('CO',  'COLORADO'),
    'connecticut':   ('CT',  'CONNECTICUT'),
    'delaware':      ('DE',  'DELAWARE'),
    'florida':       ('FL',  'FLORIDA'),
    'georgia':       ('GA',  'GEORGIA'),
    'hawaii':        ('HI',  'HAWAII'),
    'idaho':         ('ID',  'IDAHO'),
    'illinois':      ('IL',  'ILLINOIS'),
    'indiana':       ('IN',  'INDIANA'),
    'iowa':          ('IA',  'IOWA'),
    'kansas':        ('KS',  'KANSAS'),
    'kentucky':      ('KY',  'KENTUCKY'),
    'louisiana':     ('LA',  'LOUISIANA'),
    'maine':         ('ME',  'MAINE'),
    'maryland':      ('MD',  'MARYLAND'),
    'massachusetts': ('MA',  'MASSACHUSETTS'),
    'michigan':      ('MI',  'MICHIGAN'),
    'minnesota':     ('MN',  'MINNESOTA'),
    'mississippi':   ('MS',  'MISSISSIPPI'),
    'missouri':      ('MO',  'MISSOURI'),
    'montana':       ('MT',  'MONTANA'),
    'nebraska':      ('NE',  'NEBRASKA'),
    'nevada':        ('NV',  'NEVADA'),
    'new-hampshire': ('NH',  'NEW HAMPSHIRE'),
    'new-jersey':    ('NJ',  'NEW JERSEY'),
    'new-mexico':    ('NM',  'NEW MEXICO'),
    'new-york':      ('NY',  'NEW YORK'),
    'north-carolina':('NC',  'NORTH CAROLINA'),
    'north-dakota':  ('ND',  'NORTH DAKOTA'),
    'ohio':          ('OH',  'OHIO'),
    'oklahoma':      ('OK',  'OKLAHOMA'),
    'oregon':        ('OR',  'OREGON'),
    'pennsylvania':  ('PA',  'PENNSYLVANIA'),
    'rhode-island':  ('RI',  'RHODE ISLAND'),
    'south-carolina':('SC',  'SOUTH CAROLINA'),
    'south-dakota':  ('SD',  'SOUTH DAKOTA'),
    'tennessee':     ('TN',  'TENNESSEE'),
    'texas':         ('TX',  'TEXAS'),
    'utah':          ('UT',  'UTAH'),
    'vermont':       ('VT',  'VERMONT'),
    'virginia':      ('VA',  'VIRGINIA'),
    'washington':    ('WA',  'WASHINGTON'),
    'west-virginia': ('WV',  'WEST VIRGINIA'),
    'wisconsin':     ('WI',  'WISCONSIN'),
    'wyoming':       ('WY',  'WYOMING'),
}

NODE_MAP = {
    'abilene':     ('Abilene Campus',  'Abilene, TX'),
    'albuquerque': ('ABQ Campus',      'Albuquerque, NM'),
    'columbus':    ('Columbus Campus', 'Columbus, OH'),
    'saline':      ('The Barn (Saline)', 'Saline, MI'),
}

# City map: slug -> (display_name, state_name, db_variants, intro)
CITY_MAP = {
    'denver': (
        'Denver', 'Colorado',
        ['DENVER', 'Denver'],
        "Denver, Colorado is the largest city in the Project Stargate AI infrastructure supply corridor — home to over 900 companies with active UCC-1 equipment financing records in our database. As the economic hub of the Rocky Mountain region, Denver-based contractors, technology vendors, construction operators, and specialty service firms are deeply embedded in the Stargate supply ecosystem. Whether you're a salesperson, recruiter, lender, equipment vendor, SaaS company, or any B2B business wanting to reach Denver companies in the Stargate build — this directory gives you ranked, scored intelligence on every company: who their lender is, what equipment they own, when their financing matures, and how fast they're growing. Denver represents one of the highest-density concentrations of high-growth B2B prospecting targets in the Rocky Mountain West."
    ),
    'colorado-springs': (
        'Colorado Springs', 'Colorado',
        ['COLORADO SPRINGS', 'Colorado Springs'],
        "Colorado Springs is a major hub for aerospace, defense, and construction companies active in the Project Stargate AI infrastructure supply ecosystem. With over 500 companies holding active UCC-1 equipment financing records in our database, Colorado Springs businesses — spanning construction, specialty manufacturing, logistics, and technology services — represent high-value B2B prospecting targets for any vendor, lender, recruiter, or salesperson wanting to reach the Stargate supply chain in Colorado. The Colorado Springs metro has one of the highest concentrations of aerospace and defense contractors in the US, many of whom are now pivoting capacity toward AI infrastructure projects. This directory gives you ranked, scored intelligence on every Colorado Springs company in our database."
    ),
    'aurora': (
        'Aurora', 'Colorado',
        ['AURORA', 'Aurora'],
        "Aurora, Colorado is a rapidly growing industrial and commercial hub adjacent to Denver, with over 400 companies holding active UCC-1 equipment financing records in the Stargate CapEx database. Aurora-based contractors, logistics operators, construction firms, and specialty vendors are active participants in the $500B Stargate AI infrastructure buildout supply chain. For any B2B business — salespeople, lenders, equipment dealers, recruiters, SaaS vendors, insurance agents, or specialty contractors — wanting to reach Aurora companies in the Stargate ecosystem, this directory provides ranked, scored business intelligence on every company: financing stage, lender relationships, equipment type, and growth trajectory."
    ),
    'englewood': (
        'Englewood', 'Colorado',
        ['ENGLEWOOD', 'Englewood'],
        "Englewood, Colorado is home to over 240 companies with active UCC-1 equipment financing records in the Stargate CapEx database — specialty contractors, technology vendors, construction operators, and equipment-intensive businesses that are part of the broader Denver metro Stargate supply corridor. For salespeople, lenders, vendors, and B2B businesses wanting to reach Englewood companies in the AI infrastructure ecosystem, this directory provides full business intelligence: propensity scoring, lender relationships, financing maturity, and equipment collateral data."
    ),
}

STATE_INTROS = {
    'georgia': (
        "Georgia is home to nearly 4,000 companies actively involved in the Project Stargate AI infrastructure supply chain — "
        "contractors, fabricators, technology vendors, power operators, and equipment-intensive businesses driving the $500B buildout. "
        "Whether you're a salesperson looking to win new business, a vendor seeking to expand into the AI infrastructure corridor, "
        "a recruiter finding high-growth companies, or a lender identifying active borrowers — this directory gives you every "
        "Georgia company with a live UCC-1 equipment financing record, ranked by propensity score. "
        "Each company record shows who their lender is, what equipment they own, when their financing matures, and their overall "
        "growth signal — giving you the business intelligence to reach the right company at the right time. "
        "From Atlanta's commercial corridor to Savannah's industrial port companies, the Georgia Stargate directory is the most "
        "complete business intelligence resource for anyone wanting to work with, sell to, or partner with companies in the "
        "$500B AI infrastructure build."
    ),
    'colorado': (
        "Colorado is one of the most active states in the Project Stargate AI infrastructure supply chain, with over 6,800 companies "
        "holding live UCC-1 equipment financing records in our database. These are contractors, technology vendors, power systems "
        "companies, construction operators, and specialty service firms actively building and supporting the $500B Stargate corridor. "
        "For any business or salesperson wanting to reach these companies — whether to sell software, offer financing, provide staffing, "
        "win subcontracts, or deliver services — this directory provides the business intelligence you need. "
        "Every Colorado company record includes propensity scoring, lender relationships, equipment collateral type, financing maturity "
        "timeline, and geographic proximity to active Stargate build sites. "
        "Colorado's Front Range — from Fort Collins through Denver to Colorado Springs — is a dense concentration of the exact "
        "type of high-growth, equipment-intensive businesses that every B2B vendor should be prospecting right now."
    ),
    'connecticut': (
        "Connecticut is a significant node in the Project Stargate AI infrastructure supply chain, with nearly 4,000 companies "
        "holding active UCC-1 equipment financing records in our database. These businesses — spanning Hartford, Bridgeport, "
        "New Haven, and Stamford — include specialty manufacturers, technology vendors, construction firms, and equipment operators "
        "actively involved in the $500B Stargate buildout ecosystem. "
        "For any salesperson, vendor, recruiter, or lender wanting to reach companies in the Northeast Stargate corridor, "
        "this directory is your starting point. Every company record provides propensity scoring, lender data, collateral type, "
        "and financing maturity signals — the intelligence you need to know which companies are growing, what they own, "
        "who they bank with, and when they're most receptive to new business conversations. "
        "Connecticut's advanced manufacturing and aerospace heritage makes these companies particularly valuable targets for "
        "B2B vendors across software, services, staffing, insurance, logistics, and specialty contracting."
    ),
    'california': (
        "California is a major hub for companies in the Project Stargate AI infrastructure ecosystem — including technology suppliers, "
        "semiconductor vendors, precision manufacturers, and specialty contractors supporting the $500B buildout. "
        "With over 800 active UCC-1 equipment financing records tracked in our database, California-based companies from "
        "Los Angeles, San Francisco, San Jose, and Sacramento represent some of the highest-value business intelligence targets "
        "in the Stargate supply chain. "
        "Whether you're a SaaS company looking to sell into AI-adjacent businesses, a recruiter targeting high-growth tech vendors, "
        "a lender seeking prime equipment finance borrowers, or any B2B vendor wanting to reach the California Stargate ecosystem — "
        "this directory gives you ranked, scored company records with full intelligence on financing stage, lender relationships, "
        "equipment type, and growth trajectory. Know which California companies are expanding before your competition does."
    ),
    'texas': (
        "Texas is ground zero for the Project Stargate AI infrastructure buildout — anchored by the Abilene Campus, OpenAI's "
        "primary $500B data center hub, with additional build activity across Dallas, Houston, and Austin. "
        "The companies in this directory are the contractors, construction firms, power vendors, technology operators, and "
        "equipment-intensive businesses at the heart of the largest infrastructure investment in American history. "
        "For any business wanting to reach them — whether you're selling enterprise software, providing specialty services, "
        "offering equipment financing, hiring talent, delivering logistics, or winning subcontracts — this is the definitive "
        "directory of Texas companies in the Stargate ecosystem, ranked by propensity score. "
        "Each company record includes intelligence on who their lender is, what equipment they operate, when their financing "
        "matures, and their overall growth signal — giving every prospector the data needed to open the right door at the right time."
    ),
    'montana': (
        "Montana-based contractors, equipment operators, and specialty construction companies are part of the broader Project "
        "Stargate AI infrastructure supply ecosystem. With over 500 active UCC-1 equipment financing records tracked in our database, "
        "these Montana businesses provide construction, heavy equipment, rural infrastructure, and specialty services supporting "
        "the $500B Stargate buildout. "
        "For vendors, lenders, recruiters, and salespeople wanting to reach Montana companies in this ecosystem — this directory "
        "provides full business intelligence: propensity scoring, lender relationships, collateral type, and financing maturity "
        "signals. Montana companies, while fewer in number, often represent niche high-value relationships in the Stargate "
        "supply chain — exactly the kind of underprospected targets that savvy B2B salespeople find first."
    ),
    'idaho': (
        "Idaho is an emerging hub in the Project Stargate AI infrastructure supply corridor, providing key resources in construction, transport, and raw materials. Our database tracks companies across Boise, Idaho Falls, and Coeur d'Alene with active UCC-1 equipment financing records, offering critical prospecting data for outbound B2B teams."
    ),
    'new-york': (
        "New York plays a major role in the Project Stargate supply chain, delivering advanced manufacturing, technology components, and financial operations. This directory indexes New York suppliers with active UCC-1 financing statements, helping B2B vendors locate prime sales opportunities at exactly the right time."
    ),
    'massachusetts': (
        "Massachusetts contributes advanced engineering, technology research, and electronics manufacturing to the Stargate AI infrastructure corridor. Outbound sales reps can browse Massachusetts companies with live UCC-1 records to target expanding tech suppliers."
    ),
    'new-jersey': (
        "New Jersey is a vital logistics, distribution, and manufacturing node for the Stargate AI infrastructure build. This directory tracks Jersey-based suppliers and contractors with active UCC-1 equipment financing, providing ranked business intelligence for B2B prospecting."
    ),
    'arizona': (
        "Arizona hosts critical components of the Stargate Southwest compute network, specializing in precision fabrication and power engineering. Our database ranks Arizona suppliers with active equipment financing records by propensity score."
    ),
    'florida': (
        "Florida-based contractors, logistics carriers, and mechanical vendors are active participants in the Project Stargate compute corridor. This directory provides full intelligence on Florida companies with active UCC-1 statements, mapped to compute nodes."
    ),
    'wyoming': (
        "Wyoming's energy infrastructure and construction sectors support the Project Stargate AI build corridor. This directory indexes Wyoming contractors and equipment operators with live UCC-1 records, scored by buying propensity."
    ),
    'illinois': (
        "Illinois represents a central manufacturing and power distribution node for the Midwest Stargate campus network. Prospect local suppliers in Chicago and the industrial corridors with active UCC-1 equipment financing."
    ),
    'utah': (
        "Utah is a fast-growing tech and manufacturing corridor supporting Stargate compute sites. This directory indexes Utah contractors and engineering firms with active UCC-1 equipment financing."
    ),
    'oklahoma': (
        "Oklahoma-based steel fabricators, power engineers, and civil contractors support the Stargate computing corridor. Track Oklahoma companies with live UCC-1 records to capture new equipment leasing and refinance cycles."
    ),
    'michigan': (
        "Michigan and 'The Barn' compute node in Saline represent a massive expansion point in the Project Stargate AI infrastructure supply corridor, backed by Related Digital and Blackstone's $16B–$56B data center investment. This directory indexes Michigan suppliers, contractors, and steel fabricators with active UCC-1 equipment financing records to capture high-intent local prospecting opportunities."
    ),
}

NODE_INTROS = {
    'abilene': (
        "The Abilene Campus is the flagship hub of the $500B Project Stargate AI infrastructure initiative — OpenAI's primary "
        "data center in West Texas, projected to house over 100,000 AI servers and anchor the most significant technology "
        "infrastructure investment in US history. "
        "The companies listed here are the businesses nearest the Abilene Campus with active UCC-1 equipment financing records — "
        "contractors, power vendors, construction operators, technology suppliers, and equipment-intensive businesses that are "
        "actively part of or adjacent to the Stargate build. "
        "For any business wanting to reach them — whether you sell software, staffing, insurance, logistics, financing, specialty "
        "equipment, or services — this directory gives you ranked, scored company records with full intelligence on what they own, "
        "who they bank with, and when they're most ready for a business conversation. "
        "The Abilene ecosystem is one of the most concentrated clusters of high-growth B2B prospecting targets in the country right now."
    ),
    'albuquerque': (
        "The ABQ Campus — the Albuquerque node of Project Stargate's $500B AI infrastructure network — positions New Mexico as "
        "a critical hub in the distributed AI compute buildout, with Oracle and NVIDIA named as primary technology partners. "
        "The companies listed here are those nearest the Albuquerque Campus with active UCC-1 equipment financing records — "
        "construction contractors, power engineers, specialty fabricators, and equipment operators in the broader Stargate "
        "Southwest supply corridor. "
        "For any salesperson, vendor, or business development professional wanting to reach these companies — this directory is "
        "your intelligence source. Every record includes propensity scoring, lender data, collateral type, and financing maturity "
        "signals. Whether you're in software sales, specialty services, logistics, staffing, insurance, or financing — "
        "the Albuquerque Stargate ecosystem contains exactly the type of growing, equipment-intensive businesses that "
        "every B2B prospector should be targeting."
    ),
    'columbus': (
        "The Columbus Campus is Project Stargate's Midwest anchor — positioning Columbus, Ohio as a major node in the $500B "
        "AI infrastructure network and drawing on Ohio's deep manufacturing base and central logistics position. "
        "The companies listed here are those nearest the Columbus Campus with active UCC-1 equipment financing records — "
        "heavy civil contractors, electrical vendors, HVAC and cooling specialists, fabricators, and equipment-intensive "
        "businesses in the Midwest Stargate supply corridor. "
        "For any business wanting to reach these companies — whether you're selling enterprise software, providing specialty "
        "services, offering financing, delivering staffing solutions, or winning subcontracts in the AI infrastructure build — "
        "this directory provides full business intelligence on every company: who they bank with, what they own, how their "
        "financing is structured, and their overall growth trajectory. "
        "Columbus is one of the most underprospected high-growth B2B markets in the country right now."
    ),
    'saline': (
        "The Barn node in Saline, Michigan, represents a cornerstone compute campus in the Midwest Project Stargate network, powered by Related Digital and a massive $16B–$56B Blackstone investment. This directory indexes local suppliers, heavy haulers, electricians, and civil contractors operating within the immediate orbit of the Saline compute campus. Sales reps, lenders, and dealers use these ranked, scored company records to capture high-intent capital expenditure triggers and refinance cycles."
    ),
}

def get_state_faqs(state_name, state_code):
    return [
        {
            "question": f"What is the Project Stargate supply network in {state_name}?",
            "answer": f"The {state_name} Stargate supply network consists of local civil contractors, electric power vendors, HVAC engineers, and logistics carriers in {state_name} ({state_code}) with active UCC-1 filings."
        },
        {
            "question": f"How do B2B reps prospect Stargate suppliers in {state_name}?",
            "answer": f"Sales reps use {state_name} UCC-1 data to trace equipment replacement dates, lender relationships, and target accounts when they are closest to buying windows."
        },
        {
            "question": "What computing nodes are closest to this state?",
            "answer": "Project Stargate compute campuses are located in Abilene TX, Columbus OH, and Albuquerque NM, with suppliers feeding in nationwide."
        }
    ]

def get_node_faqs(node_name, node_location):
    return [
        {
            "question": f"What is the Project Stargate {node_name}?",
            "answer": f"The {node_name} is a major computing campus located in {node_location}, housing advanced AI data centers as part of the $500B Stargate network."
        },
        {
            "question": f"Who are the contractors building the {node_name}?",
            "answer": f"Contractors near the {node_name} include civil engineering companies, heavy riggers, backup power providers, and high-performance fiber installers."
        }
    ]

@app.route('/companies/state/<state_slug>')
def state_page(state_slug):
    """SEO landing page for companies by state."""
    if state_slug not in STATE_MAP:
        abort(404)
    state_code, state_name = STATE_MAP[state_slug]
    conn = get_db()
    rows = conn.execute(
        '''SELECT company_name, city, state, secured_party, lien_type,
                  propensity_score, nearest_node, days_to_lapse, filing_date
           FROM active_stargate_leads
           WHERE (UPPER(state) = ? OR UPPER(state) = ?)
           ORDER BY propensity_score DESC LIMIT 500''',
        (state_code.upper(), state_name.upper())
    ).fetchall()
    conn.close()
    companies = [dict(r) for r in rows]
    page_title = f"Project Stargate AI Infrastructure Companies in {state_name} | Stargate CapEx"
    page_desc  = (f"Browse {len(companies)} UCC-1 equipment financing companies in {state_name} "
                  f"active in the Project Stargate $500B AI infrastructure build-out. "
                  f"Ranked by propensity score.")
    h1        = f"Project Stargate Companies in {state_name}"
    canonical = f"https://stargatecapex.com/companies/state/{state_slug}"
    state_intro = STATE_INTROS.get(state_slug)
    if not state_intro:
        state_intro = (
            f"{state_name.title()} ({state_code}) is an active region within the Project Stargate AI infrastructure supply chain corridor. "
            f"This directory indexes local contractors, fabricators, logistics providers, and specialty vendors near Project Stargate nodes "
            f"holding active UCC-1 equipment financing and commercial asset liens. Prospecting teams, alternative lenders, and equipment "
            f"dealers use these ranked business intelligence records to identify active capital expenditures, track maturing credit lines, "
            f"and connect with high-intent buyers across {state_name.title()}."
        )

    return render_template('index.html',
        activity=companies,
        page_title=page_title,
        page_desc=page_desc,
        page_h1=h1,
        canonical=canonical,
        filter_label=f"{len(companies)} companies in {state_name}",
        page_intro=state_intro,
        faq_data=get_state_faqs(state_name, state_code)
    )


@app.route('/companies/node/<node_slug>')
def node_page(node_slug):
    """SEO landing page for companies by Stargate node."""
    if node_slug not in NODE_MAP:
        abort(404)
    node_name, node_location = NODE_MAP[node_slug]
    conn = get_db()
    rows = conn.execute(
        '''SELECT company_name, city, state, secured_party, lien_type,
                  propensity_score, nearest_node, days_to_lapse, filing_date
           FROM active_stargate_leads
           WHERE nearest_node = ?
           ORDER BY propensity_score DESC LIMIT 500''',
        (node_name,)
    ).fetchall()
    conn.close()
    companies = [dict(r) for r in rows]
    page_title = f"Project Stargate {node_location} Campus Companies | Stargate CapEx"
    page_desc  = (f"Browse {len(companies)} UCC-1 equipment financing companies nearest the "
                  f"Project Stargate {node_location} AI data center campus. "
                  f"Ranked by propensity score.")
    h1        = f"Project Stargate — {node_location} Campus Companies"
    canonical = f"https://stargatecapex.com/companies/node/{node_slug}"
    return render_template('index.html',
        activity=companies,
        page_title=page_title,
        page_desc=page_desc,
        page_h1=h1,
        canonical=canonical,
        filter_label=f"{len(companies)} companies near {node_location}",
        page_intro=NODE_INTROS.get(node_slug, ''),
        faq_data=get_node_faqs(node_name, node_location)
    )


@app.route('/leads')
def leads_page():
    """Server-rendered HTML lead page — fully crawlable by Google and AI bots."""
    node  = request.args.get('node', '')
    state = request.args.get('state', '')
    tier  = request.args.get('tier', '')
    search= request.args.get('search', '')
    page  = max(1, int(request.args.get('page', 1)))
    per_page = 100
    offset = (page - 1) * per_page

    where = ['1=1']
    params = []
    if node:   where.append('nearest_node_id=?'); params.append(node)
    if state:  where.append('state=?');           params.append(state.upper())
    if tier == 'priority': where.append('propensity_score>=85')
    elif tier == 'hot':    where.append('propensity_score>=65')
    if search: where.append('LOWER(company_name) LIKE ?'); params.append(f'%{search.lower()}%')

    conn = get_db()
    stats = conn.execute('''SELECT COUNT(*) total,
        SUM(CASE WHEN propensity_score>=85 THEN 1 ELSE 0 END) priority,
        SUM(CASE WHEN propensity_score>=65 AND propensity_score<85 THEN 1 ELSE 0 END) hot,
        SUM(CASE WHEN lien_type="equipment" THEN 1 ELSE 0 END) equipment,
        SUM(CASE WHEN lien_type="blanket" THEN 1 ELSE 0 END) mca
        FROM active_stargate_leads''').fetchone()
    rows = conn.execute(
        f'''SELECT company_name, city, state, days_to_lapse, lapse_date, secured_party,
                   collateral, lien_type, nearest_node, node_dist_km, propensity_score,
                   stargate_match, phone, email, filing_date
            FROM active_stargate_leads WHERE {" AND ".join(where)}
            ORDER BY propensity_score DESC LIMIT ? OFFSET ?''',
        params + [per_page, offset]
    ).fetchall()
    conn.close()

    def tier_label(s):
        if s >= 85: return 'Priority'
        if s >= 65: return 'Hot'
        if s >= 40: return 'Monitor'
        return 'Low'

    rows_html = ''
    for r in rows:
        match = {}
        try: match = json.loads(r['stargate_match'] or '{}')
        except: pass
        cats = ', '.join(match.get('cats', [])).title()
        kws  = ', '.join(match.get('kws', [])[:5])
        phone_html = f'<a href="tel:{r["phone"]}">{r["phone"]}</a>' if r['phone'] else '—'
        email_html = f'<a href="mailto:{r["email"]}">{r["email"]}</a>' if r['email'] else '—'
        rows_html += f"""
        <tr>
          <td><strong>{r['company_name']}</strong><br><small>{r['city']}, {r['state']}</small></td>
          <td>{r['lien_type'].title()}</td>
          <td>{r['secured_party'] or '—'}</td>
          <td>{r['days_to_lapse'] or '—'} days</td>
          <td>{r['lapse_date'] or '—'}</td>
          <td>{tier_label(r['propensity_score'])} ({r['propensity_score']})</td>
          <td>{r['nearest_node']}<br><small>{round(r['node_dist_km'] or 0)} km</small></td>
          <td>{cats}</td>
          <td>{phone_html}</td>
          <td>{email_html}</td>
        </tr>"""

    # Pre-compute all values as plain strings to avoid f-string double-brace issues
    total_str     = f"{stats['total']:,}"
    priority_str  = f"{stats['priority']:,}"
    hot_str       = f"{stats['hot']:,}"
    equipment_str = f"{stats['equipment']:,}"
    mca_str       = f"{stats['mca']:,}"
    row_count_str = str(len(rows))
    showing_start = str(offset + 1)
    showing_end   = str(offset + len(rows))

    prev_link = f'<a href="/leads?page={page-1}{"&node="+node if node else ""}{"&state="+state if state else ""}{"&tier="+tier if tier else ""}{"&search="+search if search else ""}" style="color:var(--cyan); margin-right:15px; text-decoration:none;">&larr; Previous Page</a>' if page > 1 else ''
    next_link = f'<a href="/leads?page={page+1}{"&node="+node if node else ""}{"&state="+state if state else ""}{"&tier="+tier if tier else ""}{"&search="+search if search else ""}" style="color:var(--cyan); text-decoration:none;">Next Page &rarr;</a>' if len(rows) == per_page else ''
    pagination_html = f'<div class="pagination" style="margin: 20px 0; font-family:\'D-DIN\', sans-serif; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">{prev_link} {next_link}</div>'

    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Stargate Capex UCC Company Database",
        "description": f"{total_str} UCC-1 equipment financing and MCA companies active in the Project Stargate AI infrastructure buildout across TX, OH, NM.",
        "url": "https://stargatecapex.com/leads",
        "creator": {"@type": "Organization", "name": "Stargate Capex", "url": "https://stargatecapex.com"},
        "keywords": ["UCC-1 companies", "equipment financing", "Project Stargate", "AI data center", "MCA companies", "construction companies", "Abilene Texas", "equipment loans"],
        "numberOfItems": stats['total'],
        "variableMeasured": ["propensity_score", "days_to_lapse", "node_dist_km", "lien_type"]
    })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Stargate Capex Company Database — Companies {showing_start} to {showing_end} | stargatecapex.com</title>
  <meta name="description" content="Browse {total_str} UCC-1 equipment financing and MCA companies for the $500B Project Stargate AI data center buildout. Contractors, fabricators, and power vendors near Abilene TX, Columbus OH, Albuquerque NM." />
  <meta name="robots" content="index, follow" />
  <link rel="canonical" href="https://stargatecapex.com/leads" />
  <script type="application/ld+json">{json_ld}</script>
  <style>
    body{{font-family:system-ui,sans-serif;margin:0;padding:20px;background:#080c14;color:#e0e0e0;font-size:13px}}
    h1{{color:#00e5ff;margin-bottom:4px;font-size:22px}}
    .sub{{color:#666;margin-bottom:24px;font-size:12px}}
    .stats{{display:flex;gap:24px;margin-bottom:24px;flex-wrap:wrap}}
    .stat{{background:#111827;padding:12px 20px;border-radius:6px;border:1px solid rgba(0,229,255,0.15)}}
    .stat b{{display:block;font-size:20px;color:#00e5ff}}
    .stat span{{font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.1em}}
    .filters{{margin-bottom:16px;display:flex;gap:10px;flex-wrap:wrap}}
    .filters a{{background:#111827;color:#00e5ff;padding:6px 14px;border-radius:4px;text-decoration:none;font-size:11px;border:1px solid rgba(0,229,255,0.2)}}
    .filters a:hover{{background:#0d1220}}
    table{{width:100%;border-collapse:collapse;font-size:11px}}
    th{{background:#111827;padding:8px 12px;text-align:left;color:#666;font-size:9px;text-transform:uppercase;letter-spacing:.12em;border-bottom:1px solid #1e2a3a;white-space:nowrap}}
    td{{padding:8px 12px;border-bottom:1px solid #0d1220;vertical-align:top}}
    tr:hover td{{background:#0d1220}}
    td strong{{color:#fff;font-size:12px}}
    td small{{color:#555}}
    a{{color:#00e5ff;text-decoration:none}}
    a:hover{{text-decoration:underline}}
    .back{{display:inline-block;margin-bottom:20px;color:#00e5ff;font-size:12px}}
    footer{{margin-top:40px;padding-top:20px;border-top:1px solid #1e2a3a;color:#333;font-size:10px;text-align:center}}
  </style>
</head>
<body>
  <a href="/" class="back">← Back to Terminal</a>
  <h1>Stargate Capex — UCC Company Database</h1>
  <p class="sub">{total_str} total companies · {priority_str} priority · {equipment_str} equipment liens · {mca_str} MCA/blanket &mdash; Updated daily</p>

  <div class="stats">
    <div class="stat"><b>{total_str}</b><span>Total Companies</span></div>
    <div class="stat"><b>{priority_str}</b><span>Priority (85+)</span></div>
    <div class="stat"><b>{hot_str}</b><span>Hot (65+)</span></div>
    <div class="stat"><b>{equipment_str}</b><span>Equipment Liens</span></div>
    <div class="stat"><b>{mca_str}</b><span>MCA / Blanket</span></div>
  </div>

  <div class="filters">
    <a href="/leads">All Companies</a>
    <a href="/leads?tier=priority">Priority</a>
    <a href="/leads?tier=hot">Hot</a>
    <a href="/leads?node=abilene">Abilene TX</a>
    <a href="/leads?node=columbus">Columbus OH</a>
    <a href="/leads?node=albuquerque">Albuquerque NM</a>
    <a href="/leads?state=TX">Texas</a>
    <a href="/leads?state=GA">Georgia</a>
    <a href="/leads?state=CO">Colorado</a>
  </div>

  <p>Showing companies {showing_start} to {showing_end} sorted by propensity score</p>

  <table>
    <thead><tr>
      <th>Company</th><th>Type</th><th>Secured Party</th>
      <th>Days Left</th><th>Lapse Date</th><th>Score</th>
      <th>Nearest Node</th><th>Categories</th><th>Phone</th><th>Email</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>

  {pagination_html}

  <footer>
    <p>Stargate Capex — UCC-1 Company Intelligence Terminal — <a href="https://stargatecapex.com">stargatecapex.com</a></p>
    <p>Data sourced from public UCC-1 filings. Project Stargate nodes: Abilene TX &middot; Columbus OH &middot; Albuquerque NM</p>
    <p><a href="/sitemap.xml">Sitemap</a> &middot; <a href="/robots.txt">robots.txt</a> &middot; <a href="/llms.txt">llms.txt</a></p>
  </footer>
</body>
</html>"""

    return html


@app.route('/companies/city/<city_slug>')
def city_page(city_slug):
    """SEO landing page for Stargate companies by city."""
    conn = get_db()
    
    if city_slug in CITY_MAP:
        city_name, state_name, db_variants, page_intro = CITY_MAP[city_slug]
        placeholders = ','.join('?' for _ in db_variants)
        rows = conn.execute(
            f'''SELECT id, company_name, city, state, lien_type, filing_date, lapse_date,
                       days_to_lapse, secured_party, propensity_score, collateral
               FROM active_stargate_leads
               WHERE city IN ({placeholders})
               ORDER BY propensity_score DESC LIMIT 500''',
            db_variants
        ).fetchall()
        conn.close()
    else:
        lead_ref = conn.execute(
            'SELECT city, state FROM active_stargate_leads WHERE replace(lower(city), " ", "-") = ? LIMIT 1',
            (city_slug,)
        ).fetchone()
        
        if not lead_ref:
            conn.close()
            abort(404)
            
        city_name = lead_ref['city']
        state_code = lead_ref['state']
        
        state_name = state_code
        for s_slug, (s_code, s_name_upper) in STATE_MAP.items():
            if s_code == state_code:
                state_name = s_name_upper.title()
                break
                
        db_variants = [city_name]
        placeholders = '?'
        rows = conn.execute(
            f'''SELECT id, company_name, city, state, lien_type, filing_date, lapse_date,
                       days_to_lapse, secured_party, propensity_score, collateral
               FROM active_stargate_leads
               WHERE city IN ({placeholders})
               ORDER BY propensity_score DESC LIMIT 500''',
            db_variants
        ).fetchall()
        conn.close()
        
        page_intro = (
            f"{city_name}, {state_name} is a key industrial region within the Project Stargate AI infrastructure supply chain corridor. "
            f"This directory indexes local civil contractors, fabrication shops, utility operators, and logistics providers holding active UCC-1 equipment financing and commercial asset liens. "
            f"Prospecting teams, lenders, and B2B vendors use these ranked intelligence profiles to capture high-intent buyers, monitor maturing debt, and track local capital expenditures."
        )
        
    companies = [dict(r) for r in rows]

    h1 = f'Project Stargate Companies in {city_name}, {state_name}'
    page_title = f'Stargate Companies {city_name} {state_name} — {len(companies):,} Company Records | Stargate CapEx'
    page_desc = f'Browse {len(companies):,} companies in {city_name}, {state_name} with active UCC-1 equipment financing in the Project Stargate AI infrastructure ecosystem. Ranked by propensity score. Business intelligence for lenders, vendors, and B2B salespeople.'
    canonical = f'https://stargatecapex.com/companies/city/{city_slug}'

    return render_template('index.html',
        companies=companies,
        activity=companies,
        page_title=page_title,
        page_desc=page_desc,
        page_h1=h1,
        page_intro=page_intro,
        canonical=canonical,
        filter_label=f'{len(companies):,} companies in {city_name}, {state_name}',
        faq_data=get_state_faqs(city_name, state_name)
    )


# ── BLOG ─────────────────────────────────────────────────────────────────────

STARGATE_BLOG_POSTS = [
    {
        'slug': 'who-is-building-project-stargate',
        'title': 'Who Is Building Project Stargate? The Complete Company Intelligence Guide',
        'date': '2026-06-06',
        'excerpt': 'Project Stargate is a $500 billion AI infrastructure investment — but who actually builds it? Here is the complete guide to the contractors, vendors, and companies in the Stargate supply chain.',
        'body': '''<p>Project Stargate is the most ambitious AI infrastructure investment in American history — a $500 billion commitment from OpenAI, SoftBank, Oracle, and a consortium of technology and investment partners to build AI data centers across the United States. But who actually builds it? The contractors, fabricators, power vendors, construction operators, and specialty service companies that form the Stargate supply chain are largely invisible to the public — and enormously valuable to every salesperson, vendor, and business wanting to reach them.</p>

<h2>What Is Project Stargate?</h2>
<p>Project Stargate was announced in January 2025, with an initial commitment of $100 billion scaling to $500 billion over four years. The buildout centers on AI compute infrastructure — massive data centers housing hundreds of thousands of NVIDIA processors, connected by high-speed fiber networks, cooled by industrial-scale systems, and powered by dedicated electrical infrastructure. The scale is unprecedented: individual campuses are projected to consume as much power as mid-sized cities.</p>

<h2>The Three Primary Campuses</h2>
<p><strong>Abilene, TX (Primary Campus):</strong> The flagship Stargate hub, anchored by OpenAI. Over 100,000 AI servers are planned, making this the largest single concentration of AI compute infrastructure in the United States. West Texas was selected for available land, proximity to power infrastructure, and favorable regulatory environment.</p>
<p><strong>Columbus, OH (Midwest Node):</strong> Ohio&#39;s manufacturing heritage, skilled construction workforce, and central logistics position make Columbus ideal for Stargate&#39;s Midwest compute hub. The Columbus campus draws contractors and vendors from Ohio, Indiana, Michigan, and Kentucky.</p>
<p><strong>Albuquerque, NM (Southwest Node):</strong> Oracle and NVIDIA are primary technology partners for the ABQ campus, which serves the Southwest region of Stargate&#39;s distributed AI compute network. New Mexico&#39;s energy infrastructure and land availability drove the site selection.</p>

<h2>What Industries Supply the Build?</h2>
<p>The Stargate supply chain spans a wide range of industries that most people don&#39;t associate with AI:</p>
<ul>
<li><strong>Heavy civil construction</strong> — site preparation, foundations, structural steel, concrete work</li>
<li><strong>Electrical engineering</strong> — power distribution systems, transformer installation, high-voltage infrastructure</li>
<li><strong>Mechanical and HVAC</strong> — industrial cooling systems for AI hardware that generates enormous heat loads</li>
<li><strong>Technology vendors</strong> — fiber cabling, networking equipment, server installation and configuration</li>
<li><strong>Logistics operators</strong> — moving billions of dollars in hardware to remote build sites on tight schedules</li>
<li><strong>Specialty contractors</strong> — waterproofing, fire suppression, security systems, backup power</li>
</ul>

<h2>Who Are the Companies?</h2>
<p>The Stargate supply chain companies are not household names. They are mid-market contractors and specialty vendors — typically doing $5 million to $500 million in annual revenue — operating under subcontract agreements with the general contractors managing each campus build. Many of them are the same companies that built hyperscale data centers for Amazon, Google, and Microsoft over the past decade, now pivoting capacity toward the Stargate build.</p>
<p>These companies are identified through UCC-1 equipment financing filings — public records that reveal what equipment a company owns, who their lender is, and when their financing matures. The Stargate CapEx Intelligence Terminal aggregates these records for companies in the Stargate supply ecosystem, ranked by propensity score and filtered by state, node, and city.</p>

<h2>How to Find Stargate Companies</h2>
<p>For any business wanting to reach companies in the Stargate supply chain — whether you sell software, provide specialty services, offer equipment financing, deliver staffing solutions, or want to win subcontracts — the Stargate CapEx Intelligence Terminal is your starting point.</p>
<p>Browse by state: <a href="/companies/state/texas">Texas</a> &middot; <a href="/companies/state/georgia">Georgia</a> &middot; <a href="/companies/state/colorado">Colorado</a> &middot; <a href="/companies/state/connecticut">Connecticut</a> &middot; <a href="/companies/state/california">California</a> &middot; <a href="/companies/state/montana">Montana</a></p>
<p>Browse by campus: <a href="/companies/node/abilene">Abilene Campus</a> &middot; <a href="/companies/node/columbus">Columbus Campus</a> &middot; <a href="/companies/node/albuquerque">Albuquerque Campus</a></p>'''
    },
    {
        'slug': 'project-stargate-abilene-campus',
        'title': 'Project Stargate Abilene Campus: Every Contractor and Vendor in the Build',
        'date': '2026-06-06',
        'excerpt': 'The Abilene Campus is the flagship Project Stargate data center hub in West Texas — the largest single AI compute investment in US history. Here is everything you need to know about who is building it.',
        'body': '''<p>The Abilene Campus is the crown jewel of Project Stargate — OpenAI&#39;s primary $500 billion AI data center hub in West Texas, and the largest single concentration of AI compute infrastructure in the United States. Understanding who builds it, supplies it, and services it is essential for any business wanting to reach the Stargate supply chain.</p>

<h2>Why Abilene?</h2>
<p>The selection of Abilene, Texas as Stargate&#39;s flagship campus was driven by several factors: abundant cheap land in the West Texas plains, access to the Texas power grid (ERCOT), proximity to natural gas and wind energy infrastructure, and a favorable regulatory environment. The campus is projected to eventually house over 100,000 NVIDIA AI processors, with construction phased over four years starting in 2025.</p>

<h2>The Scale of the Build</h2>
<p>The Abilene Campus build is not a single data center — it is a campus of multiple interconnected facilities, each housing racks of AI servers cooled by industrial systems drawing as much power as a small city. The power infrastructure alone requires dedicated transmission lines and potentially new generating capacity. Construction requires:</p>
<ul>
<li>Millions of square feet of raised-floor data center space</li>
<li>High-voltage electrical distribution systems capable of delivering hundreds of megawatts</li>
<li>Industrial cooling infrastructure handling heat loads that dwarf conventional office buildings</li>
<li>High-speed dark fiber connecting the campus to backbone internet exchange points</li>
<li>Physical security infrastructure and access control systems</li>
<li>Backup power systems including diesel generators and battery storage</li>
</ul>

<h2>The Supply Chain</h2>
<p>The Abilene Campus supply chain draws primarily from Texas-based contractors and vendors, supplemented by specialty firms from across the US. Texas companies in the Stargate CapEx database include heavy civil contractors from Houston and San Antonio, electrical engineering firms from Dallas, HVAC specialists from Austin, and logistics operators from across the state.</p>
<p>Many of these companies have active UCC-1 equipment financing records — public filings that reveal what equipment they own, who finances it, and when their agreements mature. This data is the foundation of the Stargate CapEx Intelligence Terminal, which ranks all Abilene-area Stargate companies by propensity score.</p>

<h2>Who Should Be Prospecting the Abilene Build?</h2>
<p>The Abilene Campus represents one of the most concentrated B2B opportunity clusters in the country right now:</p>
<ul>
<li><strong>Equipment vendors</strong> — construction, HVAC, electrical, and logistics equipment dealers</li>
<li><strong>Software companies</strong> — project management, fleet tracking, ERP, and field service software vendors</li>
<li><strong>Lenders and finance companies</strong> — equipment financing, construction lending, working capital</li>
<li><strong>Staffing and recruiting firms</strong> — the Abilene build requires thousands of skilled tradespeople</li>
<li><strong>Insurance agents</strong> — equipment-heavy contractors need specialized coverage</li>
<li><strong>Subcontractors</strong> — specialty firms looking to work under the primary contractors</li>
</ul>

<h2>Browse Abilene Campus Companies</h2>
<p>The Stargate CapEx Intelligence Terminal has <a href="/companies/node/abilene">the complete directory of companies near the Abilene Campus</a>, ranked by propensity score and filterable by lien type, financing maturity, and secured party. Start prospecting the Abilene build today.</p>'''
    },
    {
        'slug': 'ucc-data-sales-prospecting-stargate',
        'title': 'How Any Business Can Use Stargate CapEx Data to Find New Clients',
        'date': '2026-06-06',
        'excerpt': 'The Stargate CapEx Intelligence Terminal is not just for lenders. Any B2B salesperson, vendor, recruiter, or business wanting to reach companies in the $500B AI infrastructure build can use our data.',
        'body': '''<p>Most people assume business intelligence databases like the Stargate CapEx Intelligence Terminal are only for equipment lenders or finance companies. That assumption is wrong — and costly. The UCC-1 data and propensity signals in our database are valuable to every business that sells B2B.</p>

<h2>What the Data Actually Tells You</h2>
<p>Every company record in the Stargate CapEx database contains:</p>
<ul>
<li><strong>Company name and location</strong> — who they are and where they operate</li>
<li><strong>Secured party (lender)</strong> — who finances their equipment, revealing banking relationships</li>
<li><strong>Collateral description</strong> — what equipment they own (excavators, generators, network hardware, vehicles, CNC machines, etc.)</li>
<li><strong>Filing and lapse dates</strong> — when they entered their financing agreement and when it expires</li>
<li><strong>Propensity score</strong> — our model&#39;s prediction of how likely they are to be evaluating new business relationships right now</li>
<li><strong>Score tier</strong> — hot, warm, or cold classification for prioritization</li>
</ul>

<h2>Who Can Use This Data (Beyond Lenders)</h2>
<p><strong>Software and SaaS companies:</strong> Companies with active equipment financing are growing businesses actively managing capital assets. They buy fleet tracking software, ERP systems, field service management tools, accounting software, and dozens of other SaaS products. The collateral description tells you exactly what kind of equipment they run, so you can target with relevant messaging.</p>
<p><strong>Staffing and recruiting firms:</strong> Companies filing new UCC-1 agreements are adding capacity — and adding employees. High propensity-score companies in the Stargate ecosystem are actively hiring skilled tradespeople, project managers, engineers, and operations staff.</p>
<p><strong>Insurance agents and brokers:</strong> Equipment-heavy contractors need specialized coverage: inland marine, equipment breakdown, contractor general liability, workers&#39; comp. The collateral description tells you exactly what coverage conversations to have.</p>
<p><strong>Specialty subcontractors:</strong> Looking to win work on the Stargate build? The companies in our database include the prime contractors and specialty subs that are managing the Abilene, Columbus, and Albuquerque campus builds. Finding them, understanding their financial profile, and reaching out at the right time is how subcontractors win new work.</p>
<p><strong>Commercial real estate brokers:</strong> Companies with maturing equipment financing are often expanding facilities. High-propensity companies in the Stargate corridor are actively evaluating new locations for operations, fabrication, and staging yards.</p>
<p><strong>Any B2B salesperson:</strong> The propensity score and score tier tell you which companies are most receptive to outreach right now — not in six months. A &quot;hot&quot; tier company with a lapsing financing agreement in the Stargate corridor is a business in active decision-making mode.</p>

<h2>How to Start</h2>
<p>Browse the Stargate CapEx database by state or campus node, filter by score tier, and start with the highest-propensity companies in your target geography. Each company record gives you the business intelligence you need to make a relevant, timely first contact.</p>
<p>Browse by state: <a href="/companies/state/texas">Texas</a> &middot; <a href="/companies/state/colorado">Colorado</a> &middot; <a href="/companies/state/georgia">Georgia</a> &middot; <a href="/companies/state/connecticut">Connecticut</a></p>
<p>Browse by campus: <a href="/companies/node/abilene">Abilene</a> &middot; <a href="/companies/node/columbus">Columbus</a> &middot; <a href="/companies/node/albuquerque">Albuquerque</a></p>'''
    },
    {
        'slug': 'project-stargate-state-by-state-guide',
        'title': 'Project Stargate: State-by-State Company Intelligence Guide',
        'date': '2026-06-06',
        'excerpt': 'The $500B Project Stargate AI infrastructure build spans multiple states. Here is the complete state-by-state breakdown of companies in the Stargate supply chain, with business intelligence on each market.',
        'body': '''<p>Project Stargate&#39;s $500 billion AI infrastructure buildout is a national initiative — drawing contractors, vendors, and specialty companies from across the United States. Understanding the geographic distribution of the Stargate supply chain is essential for any business wanting to reach these companies. Here is the complete state-by-state breakdown.</p>

<h2>Texas — The Primary Build State</h2>
<p>Texas anchors the Stargate build, home to the flagship Abilene Campus and the McGregor test site. Texas-based contractors and vendors in the Stargate CapEx database include heavy civil construction firms from Houston and San Antonio, electrical engineering companies from Dallas, and logistics operators from across the state. The Texas Stargate ecosystem is the most active and highest-opportunity market for vendors and salespeople wanting to reach Stargate supply chain companies. <a href="/companies/state/texas">Browse Texas Stargate companies &rarr;</a></p>

<h2>Georgia — The Largest State Dataset</h2>
<p>Georgia has the largest population of companies in our Stargate CapEx database — nearly 4,000 active UCC-1 equipment financing records. Georgia&#39;s industrial corridor, anchored by Atlanta&#39;s commercial base and Savannah&#39;s port and logistics infrastructure, provides a dense supply of contractors, fabricators, and specialty vendors active in the Stargate ecosystem. <a href="/companies/state/georgia">Browse Georgia Stargate companies &rarr;</a></p>

<h2>Colorado — The Front Range Corridor</h2>
<p>Colorado&#39;s Front Range — from Fort Collins through Denver and Colorado Springs to Pueblo — is one of the most active states in the Stargate supply chain, with over 6,800 active company records in our database. Colorado&#39;s aerospace and defense heritage translates directly into Stargate supply chain capability. Denver, Colorado Springs, and Aurora are the key cities. <a href="/companies/state/colorado">Browse Colorado Stargate companies &rarr;</a> &middot; <a href="/companies/city/denver">Denver city directory &rarr;</a></p>

<h2>Connecticut — Northeast Manufacturing Hub</h2>
<p>Connecticut&#39;s advanced manufacturing ecosystem — built on aerospace, defense, and precision manufacturing — contributes nearly 4,000 companies to the Stargate supply chain. Hartford, Bridgeport, New Haven, and Stamford are the primary markets. <a href="/companies/state/connecticut">Browse Connecticut Stargate companies &rarr;</a></p>

<h2>California — Technology and Specialty Vendors</h2>
<p>California contributes technology suppliers, semiconductor vendors, and specialty contractors to the Stargate build. Over 800 California companies hold active UCC-1 equipment financing records in our database. Los Angeles, San Francisco, San Jose, and Sacramento are the primary markets. <a href="/companies/state/california">Browse California Stargate companies &rarr;</a></p>

<h2>Montana — Rural Infrastructure Specialists</h2>
<p>Montana-based contractors and equipment operators provide specialized rural infrastructure and construction services to the Stargate supply chain. Over 500 Montana companies are tracked in our database. <a href="/companies/state/montana">Browse Montana Stargate companies &rarr;</a></p>

<h2>How to Use This Intelligence</h2>
<p>The Stargate CapEx Intelligence Terminal gives any business or salesperson the ranked, scored company data needed to reach Stargate supply chain companies in any state. Each record shows propensity score, lender relationships, equipment type, and financing maturity — the intelligence you need to find the right company at the right time.</p>'''
    },
]


STARGATE_BLOG_FAQS = {
    'who-is-building-project-stargate': [
        {
            "question": "Who is building Project Stargate?",
            "answer": "Project Stargate is a $500B AI compute initiative built by a distributed supply chain of civil contractors, power engineers, HVAC specialists, and logistics providers."
        },
        {
            "question": "How are Stargate suppliers identified?",
            "answer": "Suppliers are tracked through active UCC-1 filings (equipment financing and MCA liens) and geocoded based on proximity to active computing nodes."
        }
    ],
    'project-stargate-abilene-campus': [
        {
            "question": "What is the Abilene Campus in Project Stargate?",
            "answer": "The Abilene Campus is OpenAI's flagship $500 billion data center hub in West Texas, projected to consume hundreds of megawatts of power."
        },
        {
            "question": "Why was Abilene chosen for the flagship hub?",
            "answer": "Abilene offers abundant land, favorable local regulation, and close proximity to major ERCOT power transmission infrastructure."
        }
    ],
    'ucc-data-sales-prospecting-stargate': [
        {
            "question": "How can sales teams use Stargate CapEx data?",
            "answer": "B2B sales reps track maturing UCC-1 filings to identify when contractors are entering their peak capital equipment replacement or refinancing windows."
        },
        {
            "question": "What business signals are contained in UCC filings?",
            "answer": "Every record contains the borrowing company's name, lender, description of financed equipment, filing date, and propensity score."
        }
    ],
    'project-stargate-state-by-state-guide': [
        {
            "question": "Where are Project Stargate suppliers located?",
            "answer": "Stargate suppliers are active nationwide, with major clusters in Georgia, Colorado, Connecticut, California, and Texas."
        },
        {
            "question": "Which state has the largest number of Stargate-connected companies?",
            "answer": "Georgia and Colorado represent the highest concentrations of Stargate-relevant companies in our UCC-1 database."
        }
    ]
}

@app.route('/blog')
def blog_index():
    return render_template('blog.html', posts=STARGATE_BLOG_POSTS, single_post=None,
        page_title='Stargate CapEx Intelligence Blog — Project Stargate Company Research',
        canonical='https://stargatecapex.com/blog')


@app.route('/blog/<slug>')
def blog_post(slug):
    post = next((p for p in STARGATE_BLOG_POSTS if p['slug'] == slug), None)
    if not post:
        abort(404)
    faq_data = STARGATE_BLOG_FAQS.get(slug, [])
    return render_template('blog.html', posts=STARGATE_BLOG_POSTS, single_post=post,
        page_title=post['title'] + ' | Stargate CapEx',
        canonical=f"https://stargatecapex.com/blog/{post['slug']}",
        faq_data=faq_data)




@app.route('/about')
def about_page():
    content = """
    <p>Stargate CapEx is a high-performance business intelligence terminal built specifically for alternative lenders, B2B sales development teams, and commercial finance brokers targeting the $500 billion Project Stargate artificial intelligence compute corridor.</p>
    <h2>Our Mission</h2>
    <p>The scale of the AI infrastructure buildout is unprecedented. Massive compute campuses consume gigawatts of power, miles of dark fiber, and thousands of high-end cooling systems. Stargate CapEx monitors Secretary of State UCC-1 filing feeds to identify active contractors, equipment operators, and logistics partners operating near these Stargate nodes whose equipment liens are maturing.</p>
    <h2>Project Stargate Nodes Covered</h2>
    <ul>
      <li><strong>Abilene Campus</strong> — Abilene, Texas</li>
      <li><strong>The Barn (Saline)</strong> — Saline, Michigan</li>
      <li><strong>Lighthouse</strong> — Port Washington, Wisconsin</li>
      <li><strong>Columbus Campus</strong> — Columbus, Ohio</li>
      <li><strong>ABQ Campus</strong> — Albuquerque, New Mexico</li>
    </ul>
    """
    return render_template('info.html',
        page_title='About Stargate CapEx',
        page_desc='About the Stargate CapEx intelligence terminal and UCC-1 company directory.',
        canonical='https://stargatecapex.com/about',
        page_heading='About Stargate CapEx',
        page_content=content)


@app.route('/services')
def services_page():
    content = """
    <p>Stargate CapEx provides structured data, outbound pipeline building, and signal tracking tools for equipment finance brokers and B2B vendors.</p>
    <h2>What We Offer</h2>
    <h2>1. Outbound Prospecting Leads</h2>
    <p>Get real-time alerts when a supplier or contractor near a Project Stargate campus files a new UCC-1 statement or has one nearing maturity. Filter by state, proximity, or custom category.</p>
    <h2>2. Refinance Propensity Scoring</h2>
    <p>Every lead is scored (from 0 to 100) using our proprietary Stargate CapEx matching engine. We rank leads based on the type of equipment financed (equipment liens vs. blanket liens), node distance, and days-to-lapse urgency.</p>
    <h2>3. Custom API Access</h2>
    <p>Access our lead intelligence platform programmatically. Build custom integrations with your CRM or outbound sales automation platforms.</p>
    """
    return render_template('info.html',
        page_title='Services & Data Solutions',
        page_desc='Structured UCC-1 data feeds, propensity scoring, and lead alerts for B2B reps.',
        canonical='https://stargatecapex.com/services',
        page_heading='Services & Data Solutions',
        page_content=content)


@app.route("/favicon.ico")
@app.route("/apple-touch-icon.png")
def favicon():
    from flask import make_response
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "portal", "apple-touch-icon.png"), "rb") as f:
            return make_response(f.read(), 200, {"Content-Type": "image/png"})
    except Exception as e:
        return str(e), 404

if __name__ == '__main__':
    print(f"[STARTUP] Stargate Capex API — http://localhost:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
