/* stargate javascript — terminal.js */
'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  leads: [], filtered: [], sortCol: 'propensity_score', sortDir: 'desc',
  minScore: 0, tier: '', node: '', stateFilter: '', lienType: '', search: '',
  expandedId: null,
  currentPage: 1,
  pageSize: 25,
};

// ── Nodes manifest ────────────────────────────────────────────────────────────
const NODES = [
  { id:'abilene',        label:'Abilene Campus',      city:'Abilene, TX',         phase:'Live — 200MW',      dot:'live'    },
  { id:'saline',         label:'The Barn',             city:'Saline, MI',          phase:'Breaking ground — $16B', dot:'active' },
  { id:'portwashington', label:'Lighthouse',           city:'Port Washington, WI', phase:'2028 — 1GW',        dot:'active'  },
  { id:'columbus',       label:'Columbus Campus',      city:'Columbus, OH',        phase:'Planned',           dot:'planned' },
  { id:'albuquerque',    label:'ABQ Campus',           city:'Albuquerque, NM',     phase:'Planned',           dot:'planned' },
];

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Timestamp ─────────────────────────────────────────────────────────────────
function tick() {
  const el = $('nav-timestamp');
  if (!el) return;
  const n = new Date();
  el.textContent = n.toLocaleString('en-US', {
    month:'short', day:'numeric', year:'numeric',
    hour:'2-digit', minute:'2-digit', second:'2-digit', hour12: false,
  }) + ' CT';
}
setInterval(tick, 1000); tick();

// ── Nodes in hero card ────────────────────────────────────────────────────────
function renderHeroNodes() {
  const el = $('hero-node-list');
  if (!el) return;
  el.innerHTML = NODES.map(n => `
    <div class="sg-node-item">
      <div class="sg-node-dot ${n.dot}"></div>
      <div>
        <div class="sg-node-name">${n.label}</div>
        <div class="sg-node-city">${n.city}</div>
        <div class="sg-node-phase">${n.phase}</div>
      </div>
    </div>
  `).join('');
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const r = await fetch('/api/stats');
    const d = await r.json();
    animCount('stat-total',    d.total    || 0);
    animCount('stat-priority', d.priority || 0);
    animCount('stat-hot',      d.hot      || 0);
    animCount('stat-monitor',  d.monitor  || 0);
    animCount('stat-equipment',d.equipment|| 0);
    animCount('stat-mca',      d.mca      || 0);
    const pct = d.total ? Math.round(((d.priority||0) + (d.hot||0)) / d.total * 100) : 0;
    setPipeline(`${d.total?.toLocaleString()} companies indexed · ${pct}% priority or hot`, pct);
  } catch(e) {
    setPipeline('DB connection error', 0);
  }
}

function animCount(id, target) {
  const el = $(id); if (!el) return;
  const start = 0, dur = 800;
  const t0 = performance.now();
  function step(t) {
    const p = Math.min((t - t0) / dur, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(ease * target).toLocaleString();
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function setPipeline(label, pct) {
  const lbl  = $('pipeline-label');
  const fill = $('pipeline-fill');
  const pctEl= $('pipeline-pct');
  if (lbl)  lbl.textContent  = label;
  if (fill) fill.style.width = Math.min(pct, 100) + '%';
  if (pctEl)pctEl.textContent= pct + '%';
}

// ── Filter dropdowns ──────────────────────────────────────────────────────────
async function populateFilters() {
  // Nodes
  const nd = $('ctrl-node');
  if (nd) {
    NODES.forEach(n => {
      const o = document.createElement('option');
      o.value = n.id; o.textContent = n.label;
      nd.appendChild(o);
    });
  }
  // States
  try {
    const r = await fetch('/api/states');
    const states = await r.json();
    const sd = $('ctrl-state');
    if (sd) {
      states.forEach(s => {
        const o = document.createElement('option');
        o.value = s.state; o.textContent = `${s.state} (${s.cnt.toLocaleString()})`;
        sd.appendChild(o);
      });
    }
  } catch(e) {}
}

// ── Load leads ────────────────────────────────────────────────────────────────
async function loadLeads() {
  showLoading(true);
  const params = new URLSearchParams({
    min_score: state.minScore,
    tier:      state.tier,
    node:      state.node,
    state:     state.stateFilter,
    lien_type: state.lienType,
    search:    state.search,
    sort:      state.sortCol,
    dir:       state.sortDir,
    limit:     1000,
  });
  try {
    const r = await fetch('/api/leads?' + params);
    state.leads = await r.json();
    renderTable(state.leads);
  } catch(e) {
    showError('Could not load leads. Is the API running on :5052?');
  } finally {
    showLoading(false);
  }
}

// ── Render table ──────────────────────────────────────────────────────────────
function tierClass(score) {
  if (score >= 85) return 'priority';
  if (score >= 65) return 'hot';
  if (score >= 40) return 'monitor';
  return 'low';
}

function lapseClass(days) {
  if (days == null || days === '') return 'lapse-cold';
  const d = parseInt(days);
  if (d <= 7)   return 'lapse-urgent';
  if (d <= 30)  return 'lapse-hot';
  if (d <= 180) return 'lapse-warm';
  return 'lapse-cold';
}

function lapseText(days, lapseDate) {
  if (days == null || days === '') return '—';
  const d = parseInt(days);
  if (lapseDate) {
    try {
      const dt = new Date(lapseDate);
      return dt.toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'});
    } catch {}
  }
  return d + ' days';
}

function volFromAge(ageMonths) {
  if (!ageMonths) return '—';
  const a = parseFloat(ageMonths);
  if (a >= 30) return '$500k – $1M+';
  if (a >= 20) return '$250k – $500k';
  if (a >= 12) return '$100k – $250k';
  return '$50k – $100k';
}

function pillsHTML(match, lienType) {
  const pills = [];
  pills.push(`<span class="pill pill-ucc">UCC</span>`);
  if (lienType === 'blanket') pills.push(`<span class="pill pill-mca">MCA</span>`);

  const cats = match?.cats || [];
  const MAP = {
    construction: ['','construction','pill-construction'],
    power:        ['','Power',       'pill-power'],
    cooling:      ['','Cooling',      'pill-cooling'],
    fiber:        ['','Fiber/IT',     'pill-fiber'],
    heavy_equipment:['','Heavy Equip','pill-heavy'],
    manufacturing:['','Mfg',         'pill-mfg'],
  };
  cats.forEach(c => {
    if (MAP[c]) {
      const [icon, label, cls] = MAP[c];
      pills.push(`<span class="pill ${cls}">${label}</span>`);
    }
  });
  return pills.slice(0,5).join('');
}

function renderTable(leads) {
  const tbody = $('leads-tbody');
  if (!tbody) return;

  $('results-n').textContent = state.leads.length.toLocaleString();
  state.currentPage = 1;
  renderPagedTable();
}

function renderPagedTable() {
  const total = Math.max(1, Math.ceil(state.leads.length / state.pageSize));
  state.currentPage = Math.max(1, Math.min(state.currentPage, total));
  const start = (state.currentPage - 1) * state.pageSize;
  const page  = state.leads.slice(start, start + state.pageSize);

  _renderRows(page);

  // Update pagination UI
  const pc = $('page-current'), pt = $('page-total');
  if (pc) pc.textContent = state.currentPage;
  if (pt) pt.textContent = total;
  const btnFirst = $('btn-page-first'), btnPrev = $('btn-page-prev');
  const btnNext  = $('btn-page-next'),  btnLast = $('btn-page-last');
  if (btnFirst) btnFirst.disabled = state.currentPage === 1;
  if (btnPrev)  btnPrev.disabled  = state.currentPage === 1;
  if (btnNext)  btnNext.disabled  = state.currentPage === total;
  if (btnLast)  btnLast.disabled  = state.currentPage === total;
}

function _renderRows(leads) {
  const tbody = $('leads-tbody');
  if (!tbody) return;

  if (!leads.length) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="sg-empty">No companies match your filters. Try lowering the min score or clearing filters.</div></td></tr>`;
    return;
  }

  tbody.innerHTML = leads.map(r => {
    const tc  = tierClass(r.propensity_score);
    const lc  = lapseClass(r.days_to_lapse);
    const pct = r.propensity_score;
    const vol = volFromAge(r.filing_age_months);
    const match = r.stargate_match || {};
    return `
    <tr class="data-row" data-id="${r.id}" onclick="toggleExpand(${r.id},this)">
      <td>
        <div class="sg-score-wrap">
          <div class="sg-score-track"><div class="sg-score-fill ${tc}" style="width:${pct}%"></div></div>
          <span class="sg-score-num ${tc}">${pct.toFixed(1)}</span>
        </div>
      </td>
      <td>
        <div class="sg-co-name">${esc(r.company_name) }</div>
        <div class="sg-pills">${pillsHTML(match, r.lien_type)}</div>
        <div class="sg-co-loc">${esc(r.city)}, ${esc(r.state)}</div>
      </td>
      <td><span class="type-badge type-${r.lien_type === 'equipment' ? 'equipment' : 'blanket'}">${r.lien_type === 'equipment' ? 'Equipment' : 'MCA/Blanket'}</span></td>
      <td style="font-size:11px;color:var(--white-60);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.secured_party || '—')}</td>
      <td style="font-size:11px;color:var(--white-60)">${r.filing_age_months ? parseFloat(r.filing_age_months).toFixed(0) + 'mo' : '—'}</td>
      <td class="${lc}">${lapseText(r.days_to_lapse, r.lapse_date)}</td>
      <td class="sg-vol">${vol}</td>
      <td>
        <div class="sg-node-cell-name">${esc(r.nearest_node || '—')}</div>
        <div class="sg-node-cell-dist">${r.node_dist_km != null ? r.node_dist_km.toFixed(0) + ' km' : ''}</div>
      </td>
      <td>
        <div class="sg-pills">${(match.kws || []).slice(0,2).map(k => `<span class="pill pill-fiber">${k}</span>`).join('')}</div>
      </td>
    </tr>
    <tr class="expand-row" id="exp-${r.id}">
      <td colspan="9">
        <div class="expand-inner">
          <div class="expand-field"><div class="expand-label">Company</div><div class="expand-value">${esc(r.company_name)}</div></div>
          <div class="expand-field"><div class="expand-label">Location</div><div class="expand-value">${esc(r.city)}, ${esc(r.state)}</div></div>
          <div class="expand-field"><div class="expand-label">Filing Date</div><div class="expand-value">${r.filing_date || '—'}</div></div>
          <div class="expand-field"><div class="expand-label">Lapse Date</div><div class="expand-value">${r.lapse_date || '—'}</div></div>
          <div class="expand-field"><div class="expand-label">Days to Lapse</div><div class="expand-value">${r.days_to_lapse ?? '—'}</div></div>
          <div class="expand-field"><div class="expand-label">Secured Party</div><div class="expand-value">${esc(r.secured_party || '—')}</div></div>
          <div class="expand-field"><div class="expand-label">Lien Type</div><div class="expand-value">${r.lien_type || '—'}</div></div>
          <div class="expand-field"><div class="expand-label">Nearest Node</div><div class="expand-value">${esc(r.nearest_node || '—')} (${r.node_dist_km?.toFixed(0) || '?'} km)</div></div>
          <div class="expand-field"><div class="expand-label">Propensity Score</div><div class="expand-value" style="color:var(--cyan)">${r.propensity_score}</div></div>
          <div class="expand-field"><div class="expand-label">Phone</div><div class="expand-value">${r.phone ? `<a href="tel:${r.phone}">${esc(r.phone)}</a>` : '—'}</div></div>
          <div class="expand-field"><div class="expand-label">Email</div><div class="expand-value">${r.email ? `<a href="mailto:${r.email}">${esc(r.email)}</a>` : '—'}</div></div>
          <div class="expand-field"><div class="expand-label">Source</div><div class="expand-value">${r.source_db?.toUpperCase() || '—'}</div></div>
          <div class="expand-field expand-collateral"><div class="expand-label">Collateral / Asset</div><div class="expand-value">${esc(r.collateral || '—')}</div></div>
          <div class="expand-field expand-collateral"><div class="expand-label">Stargate Keywords</div><div class="expand-value" style="color:var(--cyan)">${(match.kws || []).join(', ') || '—'}</div></div>
        </div>
      </td>
    </tr>`;
  }).join('');
}

function toggleExpand(id, row) {
  const expRow = $(`exp-${id}`);
  if (!expRow) return;
  const isOpen = expRow.classList.contains('open');
  // Close all
  document.querySelectorAll('.expand-row.open').forEach(r => r.classList.remove('open'));
  document.querySelectorAll('.data-row.expanded').forEach(r => r.classList.remove('expanded'));
  if (!isOpen) {
    expRow.classList.add('open');
    row.classList.add('expanded');
  }
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showLoading(on) {
  const tbody = $('leads-tbody');
  if (!tbody) return;
  if (on) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="sg-loading">
      <div class="sg-loading-ring"></div>
      <div class="sg-loading-text">Scanning Stargate UCC database...</div>
    </div></td></tr>`;
  }
}

function showError(msg) {
  const tbody = $('leads-tbody');
  if (tbody) tbody.innerHTML = `<tr><td colspan="9"><div class="sg-empty">${msg}</div></td></tr>`;
}

// ── Sorting ───────────────────────────────────────────────────────────────────
document.addEventListener('click', e => {
  const th = e.target.closest('th.sortable');
  if (!th) return;
  const col = th.dataset.col;
  if (state.sortCol === col) {
    state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    state.sortCol = col;
    state.sortDir = th.dataset.dir || 'desc';
  }
  document.querySelectorAll('th.sorted').forEach(t => t.classList.remove('sorted'));
  th.classList.add('sorted');
  $('sort-info').textContent = `Sorted by ${col.replace(/_/g,' ')} (${state.sortDir})`;
  loadLeads();
});

// ── Controls ──────────────────────────────────────────────────────────────────
function bindControls() {
  const slider = $('ctrl-min-score');
  const sliderVal = $('ctrl-score-display');
  if (slider) {
    slider.addEventListener('input', () => {
      state.minScore = +slider.value;
      if (sliderVal) sliderVal.textContent = slider.value;
      debounce(loadLeads, 300)();
    });
  }

  const els = [
    ['ctrl-tier',   v => state.tier = v],
    ['ctrl-node',   v => state.node = v],
    ['ctrl-state',  v => state.stateFilter = v],
    ['ctrl-lien',   v => state.lienType = v],
  ];
  els.forEach(([id, setter]) => {
    const el = $(id); if (!el) return;
    el.addEventListener('change', () => { setter(el.value); loadLeads(); });
  });

  const search = $('ctrl-search');
  if (search) {
    search.addEventListener('input', debounce(() => {
      state.search = search.value.trim();
      loadLeads();
    }, 400));
  }

  const refresh = $('btn-refresh');
  if (refresh) refresh.addEventListener('click', () => { loadStats(); loadLeads(); });

  // Pagination buttons
  const goPage = (delta) => {
    const total = Math.max(1, Math.ceil(state.leads.length / state.pageSize));
    const next = state.currentPage + delta;
    if (next < 1 || next > total) return;
    state.currentPage = next;
    renderPagedTable();
    document.getElementById('data-section').scrollIntoView({ behavior: 'smooth' });
  };
  const btnFirst = $('btn-page-first'), btnPrev = $('btn-page-prev');
  const btnNext  = $('btn-page-next'),  btnLast = $('btn-page-last');
  if (btnFirst) btnFirst.addEventListener('click', () => { state.currentPage = 1; renderPagedTable(); document.getElementById('data-section').scrollIntoView({behavior:'smooth'}); });
  if (btnPrev)  btnPrev.addEventListener ('click', () => goPage(-1));
  if (btnNext)  btnNext.addEventListener ('click', () => goPage(+1));
  if (btnLast)  btnLast.addEventListener ('click', () => { state.currentPage = Math.ceil(state.leads.length / state.pageSize); renderPagedTable(); document.getElementById('data-section').scrollIntoView({behavior:'smooth'}); });
}

let _debTimer = null;
function debounce(fn, ms) {
  return (...args) => {
    clearTimeout(_debTimer);
    _debTimer = setTimeout(() => fn(...args), ms);
  };
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  renderHeroNodes();
  populateFilters();
  loadStats();
  loadLeads();
  bindControls();

  // Scroll-hide pipeline when in data section
  const hero = document.getElementById('hero');
  const observer = new IntersectionObserver(entries => {
    const pipeline = document.querySelector('.sg-pipeline');
    if (!pipeline) return;
    pipeline.style.opacity = entries[0].isIntersecting ? '0' : '1';
  }, { threshold: 0.1 });
  if (hero) observer.observe(hero);
});

// ── Copy, Selection & Right-Click Security Protections ────────────────────────
(function () {
  // 1. Domain Authorization Lock (Anti-Cloning)
  const authorizedDomains = ['stargatecapex.com', 'www.stargatecapex.com', 'localhost', '127.0.0.1'];
  const hostname = window.location.hostname.toLowerCase();
  const isAuthorized = authorizedDomains.some(domain => hostname === domain || hostname.endsWith('.' + domain));
  if (!isAuthorized) {
    document.body.innerHTML = `
      <div style="
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
        background-color: #080c14;
        color: #ff4444;
        font-family: sans-serif;
        text-align: center;
        padding: 20px;
      ">
        <h1 style="font-size: 2.5rem; margin-bottom: 20px; letter-spacing: 2px;">SECURITY EXCLUSION</h1>
        <p style="font-size: 1.1rem; color: #7a9bb5; max-width: 600px; line-height: 1.6;">
          Unauthorized domain detected. Access to Stargate CapEx Intelligence Terminal is locked on this host.
        </p>
      </div>
    `;
    throw new Error('Unauthorized host domain execution prevented.');
  }

  // 2. Prevent right-click context menu
  document.addEventListener('contextmenu', e => e.preventDefault());

  // 3. Prevent drag start
  document.addEventListener('dragstart', e => e.preventDefault());

  // 4. Prevent text selection via mouse
  document.addEventListener('selectstart', e => e.preventDefault());

  // 5. Prevent copy & cut actions — also clear any selection
  document.addEventListener('copy', e => {
    e.preventDefault();
    e.clipboardData && e.clipboardData.setData('text/plain', '');
    window.getSelection && window.getSelection().removeAllRanges();
    if (typeof showToast === 'function') {
      showToast('⚠️ Copying data is disabled for terminal security.');
    }
  });
  document.addEventListener('cut', e => {
    e.preventDefault();
    e.clipboardData && e.clipboardData.setData('text/plain', '');
  });

  // 6. Clear selection constantly so nothing stays highlighted
  setInterval(() => {
    if (window.getSelection) {
      const sel = window.getSelection();
      if (sel && sel.toString().length > 0) sel.removeAllRanges();
    }
  }, 300);

  // 5. Block DevTools, Save and View Source shortcuts
  document.addEventListener('keydown', e => {
    // Ctrl+C / Cmd+C
    if ((e.ctrlKey || e.metaKey) && e.key === 'c') {
      e.preventDefault();
      if (typeof showToast === 'function') {
        showToast('⚠️ Copying data is disabled for terminal security.');
      }
    }
    // Ctrl+U / Cmd+U (View Source)
    if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
      e.preventDefault();
      if (typeof showToast === 'function') {
        showToast('⚠️ Source code view is restricted.');
      }
    }
    // Ctrl+S / Cmd+S (Save Page)
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      if (typeof showToast === 'function') {
        showToast('⚠️ Saving this page is restricted.');
      }
    }
    // F12 (Dev Tools)
    if (e.key === 'F12') {
      e.preventDefault();
    }
    // Ctrl+Shift+I / Cmd+Option+I (Inspect)
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'I' || e.key === 'i')) {
      e.preventDefault();
    }
    if ((e.ctrlKey || e.metaKey) && e.altKey && (e.key === 'I' || e.key === 'i')) {
      e.preventDefault();
    }
  });

  // 6. Active DevTools Debugger Trap
  (function () {
    function startTrap() {
      function trap() {
        try {
          (function() { return false; }['constructor']('debugger')());
        } catch (e) {}
      }
      setInterval(trap, 150);
    }
    window.addEventListener('load', () => {
      setTimeout(startTrap, 800);
    });
  })();
})();
