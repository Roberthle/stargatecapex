#!/usr/bin/env python3
"""
Stargate Capex — Flask API
Runs on $PORT (Render) or 5052 (local)
"""
import os, sqlite3, json
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder='portal', static_url_path='')

# Relative path works both locally and on Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, 'leads', 'stargate_capex.db')
PORT = int(os.environ.get('PORT', 5052))

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return send_from_directory(os.path.join(BASE_DIR, 'portal'), 'index.html')

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

if __name__ == '__main__':
    print(f"🚀 Stargate Capex API — http://localhost:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
