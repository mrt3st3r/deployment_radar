import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import json
import streamlit.components.v1 as components

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
DB_FILE = "qa_data.db"
WEB_REPOS = ["BE Web", "FE Web",  "App FE", "App BE"]
SQUADS = ["Web Squad", "App Squad"]
WEB_ENVS = ["Test", "STG"]
STATUS_OPTIONS = ["Completed", "In progress", "Blocked", "Scheduled", "N/A", "Ready for release"]

STATUS_MAP = {
    "qa_testing": "QA Testing",
    "triage": "Defect Triage",
    "fix_deploy": "Fix & Deploy",
    "code_freeze": "Code Freeze",
    "regression": "QA Regression",
    "uat": "UAT"
}
STATUS_COLS = list(STATUS_MAP.keys())
# release_status is a derived display column (auto-computed), not editable
UI_COLUMN_ORDER = ['squad', 'repo', 'env', 'release_ver'] + STATUS_COLS + ['release_status', 'blocked_reason']

# ─────────────────────────────────────────────
# DATABASE ENGINE
# ─────────────────────────────────────────────
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo TEXT, squad TEXT, release_ver TEXT, env TEXT,
                qa_testing TEXT, triage TEXT, fix_deploy TEXT,
                code_freeze TEXT, regression TEXT, uat TEXT,
                archived INTEGER DEFAULT 0, archived_at TEXT, blocked_reason TEXT,
                release_status TEXT DEFAULT 'Pending'
            )
        """)
        # Migrate existing DBs: add release_status column if missing
        try:
            conn.execute("ALTER TABLE deployments ADD COLUMN release_status TEXT DEFAULT 'Pending'")
        except Exception:
            pass  # column already exists

def compute_release_status_display(row):
    """Used only for the Deploy Radar graphic — derives a visual state from the 6 pipeline stages."""
    all_done = all(row.get(c) == "Completed" for c in STATUS_COLS)
    if row.get("release_status") == "Completed":
        return "Completed"
    if all_done:
        return "✅ Ready for Release"
    if any(row.get(c) == "Blocked" for c in STATUS_COLS):
        return "🔴 Blocked"
    if any(row.get(c) == "In progress" for c in STATUS_COLS):
        return "🔵 In Progress"
    return "⏳ Pending"

def load_data(archived=0):
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM deployments WHERE archived = ?", conn, params=(archived,))
    if df.empty:
        return pd.DataFrame(columns=['id'] + UI_COLUMN_ORDER + (['archived_at'] if archived else []))
    df['id'] = pd.to_numeric(df['id'], errors='coerce').astype('Int64')
    df['env'] = df['env'].fillna("None")
    df['release_status'] = df['release_status'].fillna("Pending")
    return df

# ─────────────────────────────────────────────
# COLOR LOGIC (for styled dataframe views)
# ─────────────────────────────────────────────
def apply_status_colors(val):
    if val == "In progress": return "background-color: #3498db; color: white; font-weight: bold;"
    if val == "Blocked": return "background-color: #e74c3c; color: white; font-weight: bold;"
    if val == "Scheduled": return "background-color: #f1c40f; color: black;"
    if val == "Completed": return "background-color: #2ecc71; color: white; font-weight: bold;"
    if val == "Ready for release": return "background-color: #9b59b6; color: white; font-weight: bold;"
    if val == "Pending": return "background-color: #555; color: #ccc;"
    return ""

# ─────────────────────────────────────────────
# PIXEL ART DEPLOY RADAR
# ─────────────────────────────────────────────
def build_pixel_radar_html(data_rows: list) -> str:
    data_json = json.dumps(data_rows)
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Press Start 2P', monospace;
    background: transparent;
    padding: 0;
    color: #e0e0e0;
  }}

  @keyframes blink {{ 0%,49%{{opacity:1}} 50%,100%{{opacity:0}} }}
  @keyframes march {{ to {{ stroke-dashoffset: -16; }} }}
  .blink {{ animation: blink 1s step-end infinite; }}

  .radar-wrap {{
    padding: 12px 14px 16px;
    position: relative;
    overflow: hidden;
    background: #0d0d0d;
    border: 3px solid #333;
    image-rendering: pixelated;
  }}
  .radar-wrap::before {{
    content: '';
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(255,255,255,.015) 3px, rgba(255,255,255,.015) 4px);
    pointer-events: none;
    z-index: 0;
  }}

  .header-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
    position: relative;
    z-index: 1;
  }}
  .header-title {{ font-size: 13px; color: #00ff88; letter-spacing: 2px; }}
  .header-live {{ font-size: 9px; color: #aaa; }}

  .env-section {{ margin-bottom: 10px; position: relative; z-index: 1; }}
  .env-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }}
  .env-name {{
    font-size: 10px;
    letter-spacing: 2px;
    padding: 4px 10px;
    border: 2px solid;
  }}
  .env-name.test {{ color: #27AE60; border-color: #27AE60; background: rgba(39,174,96,.08); }}
  .env-name.stg  {{ color: #E67E22; border-color: #E67E22; background: rgba(230,126,34,.08); }}
  .env-dot-line {{
    flex: 1;
    height: 2px;
    background: repeating-linear-gradient(90deg, currentColor 0, currentColor 4px, transparent 4px, transparent 8px);
  }}
  .env-count {{ font-size: 9px; color: #888; }}

  .deploy-row {{
    border: 2px solid;
    padding: 10px 12px;
    margin-bottom: 8px;
    position: relative;
  }}
  .deploy-row.test-row  {{ border-color: #1a5c36; background: rgba(39,174,96,.03); }}
  .deploy-row.stg-row   {{ border-color: #6b3d10; background: rgba(230,126,34,.03); }}
  .deploy-row-top {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 9px;
    flex-wrap: wrap;
  }}
  .deploy-ver   {{ font-size: 11px; color: #fff; }}
  .deploy-repo  {{ font-size: 8px; color: #aaa; }}
  .squad-badge  {{
    font-size: 7px;
    padding: 2px 7px;
    border: 1px solid;
  }}
  .squad-badge.bau    {{ color: #c084fc; border-color: #9B59B6; background: rgba(155,89,182,.15); }}
  .squad-badge.mobile {{ color: #60a5fa; border-color: #3498DB; background: rgba(52,152,219,.15); }}
  .blocked-badge {{
    font-size: 7px;
    padding: 2px 7px;
    color: #ff6b6b;
    border: 1px solid #E74C3C;
    background: rgba(231,76,60,.15);
  }}
  .done-count {{ margin-left: auto; font-size: 8px; color: #777; }}

  .stages-row {{
    display: flex;
    align-items: flex-end;
    gap: 0;
    overflow-x: auto;
  }}
  .stage-wrap {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    min-width: 62px;
  }}
  .stage-label {{
    font-size: 7px;
    color: #ccc;
    text-align: center;
    line-height: 1.3;
    white-space: nowrap;
  }}
  .stage-box {{
    width: 54px;
    height: 36px;
    border: 2px solid;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    text-align: center;
  }}
  .stage-arrow {{
    font-size: 10px;
    color: #444;
    padding: 0 1px;
    margin-bottom: 8px;
    flex-shrink: 0;
  }}

  .promote-divider {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin: 6px 0 10px;
    position: relative;
    z-index: 1;
  }}
  .promote-text {{ font-size: 9px; color: #555; letter-spacing: 1px; }}

  .backlog-section {{
    margin-top: 10px;
    padding-top: 10px;
    border-top: 2px dashed #222;
    position: relative;
    z-index: 1;
  }}
  .backlog-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }}
  .backlog-title {{ font-size: 9px; color: #999; letter-spacing: 2px; }}
  .backlog-count {{
    font-size: 8px;
    padding: 2px 7px;
    border: 1px solid #444;
    color: #888;
    background: #111;
  }}
  .backlog-cards {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .backlog-card {{
    border: 2px dashed #333;
    padding: 9px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 170px;
    background: #0a0a0a;
  }}
  .backlog-ver  {{ font-size: 10px; color: #fff; }}
  .backlog-repo {{ font-size: 8px; color: #ccc; }}
  .backlog-sq   {{ font-size: 7px; color: #aaa; }}
  .backlog-await {{ font-size: 7px; color: #888; }}

  .empty-msg {{ font-size: 9px; color: #444; text-align: center; padding: 16px; }}

  .legend-row {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid #1a1a1a;
    position: relative;
    z-index: 1;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 8px; color: #888; }}
  .legend-dot {{ width: 10px; height: 10px; border: 1.5px solid; flex-shrink: 0; }}
</style>
</head>
<body>
<div class="radar-wrap">
  <div class="header-row">
    <div class="header-title">&#9635; DEPLOY RADAR</div>
    <div class="header-live"><span class="blink" style="color:#00ff88">&#9679;</span> LIVE</div>
  </div>

  <div id="pipeline-container"></div>

  <div class="backlog-section" id="backlog-container"></div>

  <div class="legend-row">
    <div class="legend-item"><span class="legend-dot" style="background:#27AE60;border-color:#27AE60"></span>Completed</div>
    <div class="legend-item"><span class="legend-dot" style="background:#3498DB;border-color:#3498DB"></span>In progress</div>
    <div class="legend-item"><span class="legend-dot" style="background:#E74C3C;border-color:#E74C3C"></span>Blocked</div>
    <div class="legend-item"><span class="legend-dot" style="background:#F1C40F;border-color:#F1C40F"></span>Scheduled</div>
    <div class="legend-item"><span class="legend-dot" style="background:#9B59B6;border-color:#9B59B6"></span>Ready for release</div>
    <div class="legend-item"><span class="legend-dot" style="background:#E67E22;border-color:#E67E22"></span>In UAT</div>
    <div class="legend-item"><span class="legend-dot" style="background:transparent;border-color:#333;border-style:dashed"></span>Backlog</div>
  </div>
</div>

<script>
const ALL_DATA = {data_json};

const STATUS_COLOR = {{
  'Completed':         {{ bg:'#27AE60', border:'#1E8449', text:'#fff', icon:'&#10004;' }},
  'In progress':       {{ bg:'#3498DB', border:'#217DBB', text:'#fff', icon:'&#9658;' }},
  'Blocked':           {{ bg:'#E74C3C', border:'#C0392B', text:'#fff', icon:'&#10006;' }},
  'Scheduled':         {{ bg:'#F1C40F', border:'#d4ac0d', text:'#111', icon:'&#8230;' }},
  'N/A':               {{ bg:'#1a1a1a', border:'#333',    text:'#555',   icon:'&#8212;' }},
  'In UAT':            {{ bg:'#E67E22', border:'#CA6F1E', text:'#fff', icon:'&#9670;' }},
  'Ready for release': {{ bg:'#9B59B6', border:'#7D3C98', text:'#fff', icon:'&#9733;' }},
}};

const REPO_ICONS = {{
  'RDC-Frontend(SPA)':    '&#9632;',
  'DXP-RDC-Frontend(TR)': '&#9670;',
  'Head':                 '&#9650;',
  'ExternalData':         '&#9679;',
  'App FE':               '&#9638;',
  'App BE':               '&#9636;',
}};

const STAGE_KEYS   = ['qa_testing','triage','fix_deploy','code_freeze','regression','uat'];
const STAGE_LABELS = {{ qa_testing:'QA', triage:'TRIAGE', fix_deploy:'FIX+DEP', code_freeze:'FREEZE', regression:'REGRESS', uat:'UAT' }};

function isReadyToShip(row) {{
  const allStagesDone = STAGE_KEYS.every(k => row[k] === 'Completed');
  return allStagesDone && row.release_status === 'Pending';
}}

function stageBox(row, key) {{
  const val = row[key] || 'Scheduled';
  const c   = STATUS_COLOR[val] || STATUS_COLOR['Scheduled'];
  return `<div class="stage-box" style="background:${{c.bg}};border-color:${{c.border}};color:${{c.text}}">${{c.icon}}</div>`;
}}

function shipBox(pending) {{
  if (pending) {{
    return `<div class="stage-box ship-ready blink" style="background:#9B59B6;border-color:#d8b4fe;color:#fff;font-size:9px;width:72px;height:42px;border-width:3px;text-align:center;line-height:1.3;padding:4px 2px">&#9733; READY TO SHIP</div>`;
  }}
  return `<div class="stage-box" style="background:#111;border-color:#2a2a2a;color:#333;font-size:9px">&#9651;</div>`;
}}

function stagesRow(row) {{
  const ready = isReadyToShip(row);
  let html = '<div class="stages-row">';
  STAGE_KEYS.forEach((k, i) => {{
    html += `<div class="stage-wrap"><div class="stage-label">${{STAGE_LABELS[k]}}</div>${{stageBox(row, k)}}</div>`;
    html += '<div class="stage-arrow">&#8250;</div>';
  }});
  // 7th stage: READY TO SHIP — only lights up when all 6 stages are Completed and release_status is still Pending
  html += `<div class="stage-wrap" style="min-width:80px"><div class="stage-label" style="color:${{ready ? '#d8b4fe' : '#444'}}">READY TO SHIP</div>${{shipBox(ready)}}</div>`;
  html += '</div>';
  return html;
}}

function deployCard(row, envClass) {{
  const icon       = REPO_ICONS[row.repo] || '&#9632;';
  const doneCt     = STAGE_KEYS.filter(k => row[k] === 'Completed').length;
  const ready      = isReadyToShip(row);
  const isBlocked  = STAGE_KEYS.some(k => row[k] === 'Blocked');
  const squadClass = row.squad === 'BAU Squad' ? 'bau' : 'mobile';
  const blockedBadge = isBlocked
    ? `<span class="blocked-badge blink">!! BLOCKED</span>`
    : '';
  const readyBadge = ready
    ? `<span class="blink" style="font-size:7px;padding:2px 8px;color:#d8b4fe;border:1px solid #9B59B6;background:rgba(155,89,182,.2)">&#9733; READY TO SHIP</span>`
    : '';
  const borderOverride = ready ? 'border-color:#9B59B6 !important;' : '';
  return `
    <div class="deploy-row ${{envClass}}" style="${{borderOverride}}">
      <div class="deploy-row-top">
        <span class="deploy-ver">${{icon}} ${{row.release_ver}}</span>
        <span class="deploy-repo">${{row.repo}}</span>
        <span class="squad-badge ${{squadClass}}">${{row.squad.toUpperCase()}}</span>
        ${{blockedBadge}}
        ${{readyBadge}}
        <span class="done-count">${{doneCt}}/6 DONE</span>
      </div>
      ${{stagesRow(row)}}
    </div>`;
}}

function envSection(label, rows, cssClass, colorClass) {{
  if (!rows.length) return '';
  let html = `<div class="env-section">
    <div class="env-header">
      <div class="env-name ${{cssClass}}">${{label === 'Test' ? '&#129514;' : '&#128640;'}} ${{label.toUpperCase()}} ENV</div>
      <div class="env-dot-line" style="color:${{colorClass}}"></div>
      <div class="env-count">${{rows.length}} ACTIVE</div>
    </div>`;
  rows.forEach(r => {{ html += deployCard(r, cssClass + '-row'); }});
  html += '</div>';
  return html;
}}

function render() {{
  const testRows = ALL_DATA.filter(r => r.env === 'Test');
  const stgRows  = ALL_DATA.filter(r => r.env === 'STG');
  const backlog  = ALL_DATA.filter(r => r.env === 'None' || !r.env);

  let pipeHtml = '';
  pipeHtml += envSection('Test', testRows, 'test', '#27AE60');

  if (testRows.length && stgRows.length) {{
    pipeHtml += `<div class="promote-divider"><span class="promote-text">&#9472;&#9472; PROMOTE &#9472;&#9472;&#9660;</span></div>`;
  }}

  pipeHtml += envSection('STG', stgRows, 'stg', '#E67E22');

  if (!testRows.length && !stgRows.length) {{
    pipeHtml = '<div class="empty-msg">NO ACTIVE DEPLOYMENTS</div>';
  }}

  document.getElementById('pipeline-container').innerHTML = pipeHtml;

  let backlogHtml = `
    <div class="backlog-header">
      <span style="font-size:10px">&#9203;</span>
      <span class="backlog-title">BACKLOG QUEUE</span>
      <span class="backlog-count">${{backlog.length}} WAITING</span>
    </div>`;

  if (!backlog.length) {{
    backlogHtml += '<div style="font-size:7px;color:#2a2a2a">QUEUE EMPTY &#8212; INSERT RELEASE</div>';
  }} else {{
    backlogHtml += '<div class="backlog-cards">';
    backlog.forEach(r => {{
      const icon = REPO_ICONS[r.repo] || '&#9632;';
      backlogHtml += `
        <div class="backlog-card">
          <div class="backlog-ver">${{icon}} ${{r.release_ver}}</div>
          <div class="backlog-repo">${{r.repo}}</div>
          <div class="backlog-sq">${{r.squad}}</div>
          <div class="backlog-await blink">AWAITING DEPLOY</div>
        </div>`;
    }});
    backlogHtml += '</div>';
  }}

  document.getElementById('backlog-container').innerHTML = backlogHtml;
}}

render();
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────
# APP START
# ─────────────────────────────────────────────
st.set_page_config(page_title="Release Radar", layout="wide")
init_db()

with st.sidebar:
    st.header("➕ Add New Record")
    with st.form("add_form", clear_on_submit=True):
        s_squad = st.selectbox("Squad", SQUADS)
        s_repo = st.selectbox("Repository", WEB_REPOS)
        s_ver = st.text_input("Release Version")
        s_env = st.selectbox("Target Env", ["None"] + WEB_ENVS)
        if st.form_submit_button("Add Record"):
            if s_ver:
                with get_db_connection() as conn:
                    conn.execute("""
                        INSERT INTO deployments (repo, squad, release_ver, env, qa_testing, triage, fix_deploy, code_freeze, regression, uat)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (s_repo, s_squad, s_ver, s_env, "Scheduled","Scheduled","Scheduled","Scheduled","Scheduled","Scheduled"))
                st.rerun()



st.title("📡 Release Radar")

df_full = load_data(0)
squad_filter = st.radio("🔍 Filter by Squad", options=["All Squads"] + SQUADS, horizontal=True)
df = df_full[df_full['squad'] == squad_filter].copy() if squad_filter != "All Squads" else df_full.copy()

if df.empty:
    st.info(f"No active records for {squad_filter}.")
else:
    # 1. PIXEL ART DEPLOY RADAR (replaces old Plotly graph)
    st.subheader("🕹️ Deploy Radar")
    radar_rows = df.copy()
    radar_rows['env'] = radar_rows['env'].fillna("None")
    # Convert Int64 id to plain int so json.dumps doesn't choke
    radar_rows['id'] = radar_rows['id'].astype(object).where(radar_rows['id'].notna(), None)
    radar_rows['id'] = radar_rows['id'].apply(lambda x: int(x) if x is not None else None)
    row_dicts = radar_rows[['id','repo','squad','release_ver','env'] + STATUS_COLS + ['release_status']].to_dict('records')
    pixel_html = build_pixel_radar_html(row_dicts)
    components.html(pixel_html, height=650, scrolling=True)

    # 2. LIVE STATUS PREVIEW
    st.subheader("🛰️ Live Status Preview")
    radar_view = df[df['env'] != "None"].copy()
    if not radar_view.empty:
        style_cols = STATUS_COLS + ['release_status']
        st.dataframe(
            radar_view[UI_COLUMN_ORDER].style.map(apply_status_colors, subset=style_cols),
            width="stretch", hide_index=True
        )
    else:
        st.caption("No active deployments in Test/STG.")

    # 3. PIPELINE
    st.divider()
    st.subheader("✏️ Pipeline")

    # Add a "Select" checkbox column for manual row deletion
    pipeline_df = df[['id'] + UI_COLUMN_ORDER].copy()
    pipeline_df.insert(0, "Select", False)

    edited_df = st.data_editor(
        pipeline_df,
        column_config={
            "Select": st.column_config.CheckboxColumn("🗑️ Select", help="Check rows to delete", default=False),
            "id": None,
            "env": st.column_config.SelectboxColumn("Env", options=["None"] + WEB_ENVS),
            **{col: st.column_config.SelectboxColumn(STATUS_MAP[col], options=STATUS_OPTIONS) for col in STATUS_COLS},
            "release_status": st.column_config.SelectboxColumn(
                "🚀 Release Status",
                options=["Pending", "Completed"],
                help="Set to Completed to archive this release."
            ),
        },
        hide_index=True, width="stretch", key="pipeline_editor",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Save All Changes", type="primary", use_container_width=True):
            edits = st.session_state.get("pipeline_editor", {}).get("edited_rows", {})
            if edits:
                conn = get_db_connection()
                for row_idx, changes in edits.items():
                    # Skip the synthetic "Select" column — it's not a DB field
                    db_changes = {k: v for k, v in changes.items() if k != "Select"}
                    if not db_changes:
                        continue
                    db_id = int(df.iloc[int(row_idx)]['id'])
                    for field, value in db_changes.items():
                        conn.execute(f"UPDATE deployments SET {field}=? WHERE id=?", (value, db_id))
                    # Archive ONLY if release_status was explicitly set to Completed in this save
                    if db_changes.get("release_status") == "Completed":
                        conn.execute(
                            "UPDATE deployments SET archived=1, archived_at=? WHERE id=?",
                            (datetime.now().strftime("%Y-%m-%d %H:%M"), db_id)
                        )
                conn.commit()
                conn.close()
                st.rerun()

    with col2:
        if st.button("🗑️ Delete Selected Rows", type="secondary", use_container_width=True):
            # Rows where the "Select" checkbox is True
            selected_rows = edited_df.index[edited_df["Select"] == True].tolist()
            if selected_rows:
                conn = get_db_connection()
                for row_idx in selected_rows:
                    db_id = int(df.iloc[int(row_idx)]['id'])
                    conn.execute("DELETE FROM deployments WHERE id=?", (db_id,))
                conn.commit()
                conn.close()
                st.success(f"✓ Deleted {len(selected_rows)} row(s)")
                st.rerun()
            else:
                st.warning("⚠️ No rows selected for deletion. Tick the checkbox on the row(s) you want to remove.")

    # 4. BACKLOG
    st.divider()
    st.subheader("📂 Release Backlog")
    backlog = df[df['env'] == "None"]
    if not backlog.empty:
        style_cols = STATUS_COLS + ['release_status']
        st.dataframe(
            backlog[['squad', 'repo', 'release_ver'] + STATUS_COLS + ['release_status']].style.map(apply_status_colors, subset=style_cols),
            width="stretch", hide_index=True
        )

# 5. ARCHIVE SECTION
st.divider()
st.subheader("📦 Archived Releases")
df_archived = load_data(1)
if not df_archived.empty:
    st.dataframe(df_archived[['archived_at', 'squad', 'repo', 'release_ver']], width="stretch", hide_index=True)
    if st.button("🧹 Clear Archive (Delete All Completed)"):
        with get_db_connection() as conn:
            conn.execute("DELETE FROM deployments WHERE archived = 1")
        st.rerun()
else:
    st.write("No archived releases.")