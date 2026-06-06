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

@app.route('/')
def index():
    """Serve homepage — inject top companies as SSR for Google indexing."""
    try:
        conn = get_db()
        rows = conn.execute(
            '''SELECT company_name, city, state, secured_party, lien_type,
                      propensity_score, nearest_node, days_to_lapse, filing_date
               FROM stargate_leads
               ORDER BY propensity_score DESC LIMIT 25'''
        ).fetchall()
        conn.close()
        activity = [dict(r) for r in rows]
    except Exception:
        activity = []
    return render_template('index.html', activity=activity)

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
        FROM stargate_leads''').fetchone()
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
              FROM stargate_leads
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
                           FROM stargate_leads
                           GROUP BY nearest_node_id
                           ORDER BY cnt DESC''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/states')
def api_states():
    conn = get_db()
    rows = conn.execute('''SELECT state, COUNT(*) cnt
                           FROM stargate_leads
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
    total = conn.execute('SELECT COUNT(*) FROM stargate_leads').fetchone()[0]
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
  <url>
    <loc>https://stargatecapex.com/companies/state/georgia</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/companies/state/colorado</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/companies/state/connecticut</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/companies/state/california</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/companies/state/texas</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/companies/state/montana</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>
  <!-- Node landing pages -->
  <url>
    <loc>https://stargatecapex.com/companies/node/abilene</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/companies/node/albuquerque</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/companies/node/columbus</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
    <lastmod>{today}</lastmod>
  </url>
  <!-- Legacy query-string pages -->
  <url>
    <loc>https://stargatecapex.com/leads?tier=priority</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/leads?node=abilene</loc>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/leads?node=columbus</loc>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
    <lastmod>{today}</lastmod>
  </url>
  <url>
    <loc>https://stargatecapex.com/leads?node=albuquerque</loc>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
    <lastmod>{today}</lastmod>
  </url>
</urlset>"""
    return Response(xml, mimetype='application/xml')


@app.route('/sitemap-child-<int:page>.xml')
def sitemap_child(page):
    """Paginated company sitemaps — 5000 per page covering all 16k+ companies."""
    per_page = 5000
    offset = (page - 1) * per_page
    conn = get_db()
    rows = conn.execute(
        'SELECT company_name, city, state FROM stargate_leads ORDER BY propensity_score DESC LIMIT ? OFFSET ?',
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
        FROM stargate_leads''').fetchone()
    top = conn.execute(
        "SELECT company_name, city, state, nearest_node, propensity_score, lien_type FROM stargate_leads ORDER BY propensity_score DESC LIMIT 20"
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
        FROM stargate_leads''').fetchone()
    top = conn.execute(
        """SELECT company_name, city, state, nearest_node,
                  propensity_score, lien_type, secured_party, days_to_lapse
           FROM stargate_leads ORDER BY propensity_score DESC LIMIT 100"""
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
    'georgia':     ('GA',  'Georgia'),
    'colorado':    ('CO',  'Colorado'),
    'connecticut': ('CT',  'Connecticut'),
    'california':  ('CA',  'California'),
    'texas':       ('TX',  'Texas'),
    'montana':     ('MT',  'Montana'),
}

NODE_MAP = {
    'abilene':     ('Abilene Campus',  'Abilene, TX'),
    'albuquerque': ('ABQ Campus',      'Albuquerque, NM'),
    'columbus':    ('Columbus Campus', 'Columbus, OH'),
}


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
           FROM stargate_leads
           WHERE (state = ? OR state = ?)
           ORDER BY propensity_score DESC LIMIT 500''',
        (state_code, state_name)
    ).fetchall()
    conn.close()
    companies = [dict(r) for r in rows]
    page_title = f"Project Stargate AI Infrastructure Companies in {state_name} | Stargate CapEx"
    page_desc  = (f"Browse {len(companies)} UCC-1 equipment financing companies in {state_name} "
                  f"active in the Project Stargate $500B AI infrastructure build-out. "
                  f"Ranked by propensity score.")
    h1        = f"Project Stargate Companies in {state_name}"
    canonical = f"https://stargatecapex.com/companies/state/{state_slug}"
    return render_template('index.html',
        activity=companies,
        page_title=page_title,
        page_desc=page_desc,
        page_h1=h1,
        canonical=canonical,
        filter_label=f"{len(companies)} companies in {state_name}"
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
           FROM stargate_leads
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
        filter_label=f"{len(companies)} companies near {node_location}"
    )


@app.route('/leads')
def leads_page():
    """Server-rendered HTML lead page — fully crawlable by Google and AI bots."""
    node  = request.args.get('node', '')
    state = request.args.get('state', '')
    tier  = request.args.get('tier', '')
    search= request.args.get('search', '')

    where = ['1=1']
    params = []
    if node:   where.append('nearest_node_id=?'); params.append(node)
    if state:  where.append('state=?');           params.append(state.upper())
    if tier == 'priority': where.append('propensity_score>=85')
    elif tier == 'hot':    where.append('propensity_score>=65')
    if search: where.append('LOWER(company_name) LIKE ?'); params.append(f'%{search.lower()}%')
    params.append(500)

    conn = get_db()
    stats = conn.execute('''SELECT COUNT(*) total,
        SUM(CASE WHEN propensity_score>=85 THEN 1 ELSE 0 END) priority,
        SUM(CASE WHEN propensity_score>=65 AND propensity_score<85 THEN 1 ELSE 0 END) hot,
        SUM(CASE WHEN lien_type="equipment" THEN 1 ELSE 0 END) equipment,
        SUM(CASE WHEN lien_type="blanket" THEN 1 ELSE 0 END) mca
        FROM stargate_leads''').fetchone()
    rows = conn.execute(
        f'''SELECT company_name, city, state, days_to_lapse, lapse_date, secured_party,
                   collateral, lien_type, nearest_node, node_dist_km, propensity_score,
                   stargate_match, phone, email, filing_date
            FROM stargate_leads WHERE {" AND ".join(where)}
            ORDER BY propensity_score DESC LIMIT ?''',
        params
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
  <title>Stargate Capex Company Database — {row_count_str} UCC Companies | stargatecapex.com</title>
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

  <p>Showing top {row_count_str} companies sorted by propensity score</p>

  <table>
    <thead><tr>
      <th>Company</th><th>Type</th><th>Secured Party</th>
      <th>Days Left</th><th>Lapse Date</th><th>Score</th>
      <th>Nearest Node</th><th>Categories</th><th>Phone</th><th>Email</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>

  <footer>
    <p>Stargate Capex — UCC-1 Company Intelligence Terminal — <a href="https://stargatecapex.com">stargatecapex.com</a></p>
    <p>Data sourced from public UCC-1 filings. Project Stargate nodes: Abilene TX &middot; Columbus OH &middot; Albuquerque NM</p>
    <p><a href="/sitemap.xml">Sitemap</a> &middot; <a href="/robots.txt">robots.txt</a> &middot; <a href="/llms.txt">llms.txt</a></p>
  </footer>
</body>
</html>"""

    return html




if __name__ == '__main__':
    print(f"🚀 Stargate Capex API — http://localhost:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
