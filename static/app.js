const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];

const app = {
  meta: null,
  dashboard: null,
  players: null,
  items: null,
  sets: null,
  schemas: null,
  route: 'command',
  tableCache: new Map(),
  page: 1,
  pageSize: 40,
  crudResources: null,
  crudSchemaCache: new Map(),
  runtimeGroups: null,
  commandCenter: null,
  quality: null,
  resourceAssets: null,
};

const pageEl = $('#page');
const noticeEl = $('#notice');
const titleEl = $('#pageTitle');
const eyebrowEl = $('#pageEyebrow');
const modePill = $('#modePill');
const stagedCount = $('#stagedCount');
const drawer = $('#drawer');
const drawerBackdrop = $('#drawerBackdrop');
const advancedToggle = $('#advancedToggle');

function advancedModeEnabled(){ return localStorage.getItem('lk_admin_advanced_v1') === '1'; }
function applyAdvancedMode(){
  const on=advancedModeEnabled();
  $$('.advanced-only').forEach(el=>el.classList.toggle('hidden',!on));
  $('#gcReward')?.closest('.field')?.classList.add('hidden');
  if(advancedToggle) advancedToggle.textContent=on?'⚙ Ẩn nâng cao':'⚙ Hiện nâng cao';
}
if(advancedToggle){ advancedToggle.onclick=()=>{
  const next=!advancedModeEnabled();
  localStorage.setItem('lk_admin_advanced_v1',next?'1':'0');
  applyAdvancedMode();
  if(!next && ['dashboard','contentmedia','character','world','progression','social','economy','runtime','discordops','ops','bulk','database','staged'].includes(app.route)) location.hash='#command';
};}

const RARITY_ORDER = ['COMMON','UNCOMMON','RARE','EPIC','LEGENDARY','MYTHIC','ANCIENT','DIVINE','RELIC','GOD'];
const RARITY_VI={COMMON:'Phổ thông',UNCOMMON:'Tinh luyện',RARE:'Quý hiếm',EPIC:'Sử thi',LEGENDARY:'Huyền thoại',MYTHIC:'Thần thoại',ANCIENT:'Thái cổ',DIVINE:'Thiên đạo',RELIC:'Di vật',GOD:'Chí tôn'};
const SLOT_VI={HELM:'Mũ',CHEST:'Áo giáp',SHOULDER:'Giáp vai',AMULET:'Dây chuyền',BOOTS:'Giày',RING:'Nhẫn',OFF_HAND:'Pháp bảo tay phụ',WEAPON:'Vũ khí',PET:'Linh thú'};
const CONTENT_FAVORITES = ['content.race_defs','content.path_defs','content.realm_defs','content.affinity_defs','content.technique_defs','content.enemy_defs','content.region_defs','content.research_defs'];
const LIVEOPS_TABLES = ['platform.feature_flags','liveops.event_defs','liveops.events','liveops.leaderboards','liveops.merchant_rotations','commerce.offer_defs','competitive.seasons'];
const OPS_TABLES = ['ops.abuse_signals','ops.compensation_cases','ops.player_sanctions','ops.audit_logs','platform.outbox_events','platform.scheduled_actions','platform.idempotency_records'];

const DISCORD_OPS_TABLES = ['identity.discord_guild_bindings','identity.discord_links','identity.discord_link_events','identity.interaction_refs','media.guild_media_settings'];
const DOMAIN_CONFIG = {
  character: {
    title:'Nhân vật & Tu luyện', eyebrow:'ADMIN / CHARACTER CONFIG',
    resources:['characters','races','paths','affinities','bloodlines','realms','sects','professions','techniques','tags','path-starting-techniques','technique-tags','talent-nodes','cultivation-stages','party-combat-rules'],
    runtime:['hero.player_heroes','hero.hero_affinities','hero.hero_bloodlines','hero.hero_techniques','hero.technique_loadouts','hero.breakthrough_attempts','hero.voice_cultivation_sessions']
  },
  world: {
    title:'Thế giới & PvE', eyebrow:'ADMIN / WORLD & PVE',
    resources:['regions','nodes','enemies','floor-profiles','monster-rewards','combat-profiles','section-rules','adventure-encounter-profiles','faction-bosses','boss-reward-rules','travel-floors','quest-defs'],
    runtime:['adventure.adventure_runs','adventure.player_exploration_progress','adventure.player_region_progress','combat.combat_instances','combat.combat_settlements','combat.combat_events']
  },
  progression: {
    title:'Kingdom & Progression', eyebrow:'ADMIN / PROGRESSION',
    resources:['buildings','research','march-unlocks','recipes','forge-recipes'],
    runtime:['kingdom.player_kingdoms','kingdom.kingdom_buildings','kingdom.construction_jobs','kingdom.player_research','kingdom.research_jobs','kingdom.production_sites','march.player_march_slots','march.hunt_loops','march.gather_jobs','march.resource_sites']
  },
  social: {
    title:'Commander & Clan', eyebrow:'ADMIN / SOCIAL SYSTEMS',
    resources:['commander-defs','clan-tech-defs','clan-building-defs','clan-quest-defs','clan-boss-defs'],
    runtime:['commander.player_commanders','commander.commander_presets','clan.clans','clan.clan_members','clan.clan_technology','clan.clan_buildings','clan.clan_bosses','clan.clan_boss_attempts','competitive.arena_matches','competitive.clan_sieges']
  },
  economy: {
    title:'Economy & Market', eyebrow:'ADMIN / ECONOMY',
    resources:['assets','rarity-policy','affix-combos','equipment-stats','offers','wheel-rules','market-rules'],
    runtime:['economy.ledger_accounts','economy.ledger_operations','economy.ledger_entries','economy.reward_grants','market.listings','market.direct_trade_offers','market.item_transfers','commerce.payments','commerce.refunds','commerce.entitlements']
  },
  liveops: {
    title:'LiveOps & Events', eyebrow:'ADMIN / LIVEOPS CONTROL',
    resources:['feature-flags','event-defs','leaderboards','merchant-rotations','offers','seasons'],
    runtime:['liveops.events','liveops.player_event_progress','liveops.leaderboard_entries','commerce.offer_instances','platform.scheduled_actions','platform.outbox_events']
  },
  discordops: {
    title:'Discord Operations', eyebrow:'ADMIN / DISCORD OPS',
    resources:['media-settings'],
    runtime:['identity.discord_guild_bindings','identity.discord_links','identity.discord_link_events','identity.interaction_refs','platform.outbox_events']
  }
};

function esc(v) {
  return String(v ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}
function fmt(v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'Có' : 'Không';
  if (typeof v === 'number') return new Intl.NumberFormat('vi-VN').format(v);
  if (Array.isArray(v)) return v.join(', ');
  if (typeof v === 'object') return Object.entries(v).map(([k,val])=>`${friendlyField(k)}: ${Array.isArray(val)?val.join(', '):(typeof val==='object'?Object.keys(val).length+' mục':fmt(val))}`).join(' · ');
  return String(v);
}
const FIELD_LABELS={code:'Mã',display_name:'Tên hiển thị',display_name_vi:'Tên hiển thị',kind:'Loại vòng quay',rarity:'Phẩm chất',weight:'Trọng số tỷ lệ (tự chuẩn hóa về 100%)',vitality_pct:'Sinh lực (%)',martial_pct:'Võ lực (%)',mystic_pct:'Pháp lực (%)',armor_pct:'Giáp (%)',ward_pct:'Kháng phép (%)',speed_pct:'Tốc độ (%)',crit_pct:'Chí mạng (%)',penetration_pct:'Xuyên giáp (%)',cultivation_pct:'Tu luyện (%)',image_url:'Ảnh / sticker',lore:'Mô tả nổi bật',title:'Tiêu đề',description:'Mô tả',color_rarity:'Màu theo phẩm chất',thumbnail_url:'Ảnh giao diện',footer:'Chân thẻ',message_qi:'Tu vi mỗi tin nhắn',message_minimum_characters:'Ký tự tối thiểu',message_cooldown_seconds:'Hồi tin nhắn (giây)',message_daily_cap:'Giới hạn Tu vi/ngày',voice_qi_per_minute:'Tu vi voice/phút',music_bonus_percent:'Thưởng nhạc (%)',music_gold_per_minute:'Phí nhạc/phút',asset_type:'Loại tài sản',integrity_tier:'Mức bảo vệ',precision_scale:'Số lẻ',transferable:'Có thể chuyển',status:'Trạng thái',level:'Cấp',max_level:'Cấp tối đa',chance_bps:'Tỷ lệ',chance_percent:'Tỷ lệ (%)',minimum_quantity:'Số lượng tối thiểu',maximum_quantity:'Số lượng tối đa',craft_cost:'Chi phí chế tạo',created_at:'Ngày tạo',updated_at:'Cập nhật lúc',metadata:'Thông tin bổ sung'};
function friendlyField(name){return FIELD_LABELS[name]||String(name||'').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());}
Object.assign(FIELD_LABELS,{family:'Chế độ chiến đấu',enemy_code:'Mã quái / Tầng:Phòng',hp:'HP tối đa',martial_power:'Công vật lý',mystic_power:'Công phép',armor:'Giáp',ward:'Kháng phép',speed:'Tốc độ',enabled:'Dùng base này trong trận mới',stage_no:'Tầng',chamber_no:'Phòng',mode:'Chế độ',reward_milestone:'Thưởng khi vượt',checkpoint:'Mốc lưu',modifier_budget:'Ngân sách hiệu ứng',base_stats:'Chỉ số gốc',skills:'Kỹ năng',max_hp:'HP chung của boss',attempts_per_window:'Lượt đánh mỗi đợt',hp_mult:'Hệ số HP',damage_mult:'Hệ số sát thương',armor_mult:'Hệ số giáp',stat_profile:'Chỉ số nhân vật',mechanic_params:'Cơ chế đặc biệt',config_version_id:'Phiên bản cấu hình',version:'Phiên bản base'});
function technicalColumn(col){return ['metadata','evidence','evidence_json','state_json','generation_snapshot','rng_evidence'].includes(col.column_name)||col.column_name.endsWith('_id');}
function fmtAmount(v) {
  if (v === null || v === undefined || v === '') return '0';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 8 }).format(n);
}
function trunc(v, n=54) {
  const s = fmt(v);
  return s.length > n ? s.slice(0, n-1) + '…' : s;
}
function rarityBadge(r) {
  if (!r) return '<span class="badge">—</span>';
  return `<span class="badge rarity r-${esc(r)}">${esc(RARITY_VI[r]||r)}</span>`;
}
function statusBadge(v) {
  const on = v === true || ['ACTIVE','OPEN','RUNNING','ENABLED','SUCCEEDED'].includes(String(v).toUpperCase());
  return `<span class="badge ${on?'on':'off'}">${esc(fmt(v))}</span>`;
}
function showNotice(msg, type='') {
  noticeEl.textContent = msg;
  noticeEl.className = `notice ${type}`.trim();
}
function hideNotice() { noticeEl.className = 'notice hidden'; }

async function api(path, opts={}) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`);
  return body;
}

function getStaged() {
  try { return JSON.parse(localStorage.getItem('lk_admin_staged_v1') || '{}'); }
  catch { return {}; }
}
function setStaged(data) {
  localStorage.setItem('lk_admin_staged_v1', JSON.stringify(data));
  updateStagedCount();
}
function updateStagedCount() {
  stagedCount.textContent = Object.keys(getStaged()).length;
}
function stageItem(item, patch) {
  const all = getStaged();
  all[item.item_def_id] = {
    entity: 'inventory.item_defs',
    id: item.item_def_id,
    code: item.item_code,
    name: item.item_name,
    patch,
    staged_at: new Date().toISOString()
  };
  setStaged(all);
}

function sqlString(s) { return `'${String(s).replaceAll("'", "''")}'`; }
function arraySql(arr) {
  if (arr == null) return 'NULL';
  return `ARRAY[${arr.map(x => sqlString(x)).join(', ')}]::varchar(64)[]`;
}
function jsonSql(v) { return `${sqlString(JSON.stringify(v))}::jsonb`; }
function patchToSql(change) {
  const pairs = [];
  for (const [k,v] of Object.entries(change.patch || {})) {
    if (['display_name_vi','item_type','family_code','equipment_slot','rarity','bind_rule','affix_combo_code','set_code','set_name'].includes(k)) pairs.push(`${k}=${v == null || v === '' ? 'NULL' : sqlString(v)}`);
    else if (['transferable','stackable'].includes(k)) pairs.push(`${k}=${v ? 'TRUE':'FALSE'}`);
    else if (k === 'max_stack') pairs.push(`${k}=${v == null || v === '' ? 'NULL' : Number(v)}`);
    else if (k === 'tags') pairs.push(`${k}=${arraySql(v)}`);
    else if (['base_stats','base_effects','salvage_rule'].includes(k)) pairs.push(`${k}=${jsonSql(v)}`);
  }
  return `UPDATE inventory.item_defs\nSET ${pairs.join(',\n    ')}\nWHERE id=${sqlString(change.id)}::uuid; -- ${change.code}`;
}
function allStagedSql() {
  const changes = Object.values(getStaged());
  if (!changes.length) return '-- Không có staged changes.\n';
  return `-- Lost Kingsland Admin staged changes\n-- Generated: ${new Date().toISOString()}\n-- Review before applying to the gameplay database.\n\nBEGIN;\n\n${changes.map(patchToSql).join('\n\n')}\n\n-- COMMIT;  -- Bỏ comment sau khi review\nROLLBACK; -- Mặc định an toàn: script chưa tự commit\n`;
}
function downloadText(name, text) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], {type:'text/plain;charset=utf-8'}));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function setPageMeta(title, eyebrow='ADMIN') {
  titleEl.textContent = title;
  eyebrowEl.textContent = eyebrow;
}
function setActiveNav(route) {
  $$('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.route === route));
}

function openDrawer(title, eyebrow, html) {
  drawer.classList.remove('drawer-player','drawer-wide');
  $('#drawerTitle').textContent = title;
  $('#drawerEyebrow').textContent = eyebrow;
  $('#drawerBody').innerHTML = html;
  drawer.classList.remove('hidden');
  drawerBackdrop.classList.remove('hidden');
  applyAdvancedMode();
}
function closeDrawer() {
  drawer.classList.remove('drawer-player','drawer-wide');
  drawer.classList.add('hidden');
  drawerBackdrop.classList.add('hidden');
}
$('#drawerClose').addEventListener('click', closeDrawer);
drawerBackdrop.addEventListener('click', closeDrawer);

function itemIcon(item) {
  const label = (item.equipment_slot || item.family_code || 'IT').slice(0,2);
  if (item.image_url) return `<div class="item-thumb r-${esc(item.rarity || 'COMMON')}"><img src="${esc(item.image_url)}" alt="" onerror="this.parentElement.classList.add('broken');this.remove()"><span>${esc(label)}</span></div>`;
  return `<div class="item-icon r-${esc(item.rarity || 'COMMON')}">${esc(label)}</div>`;
}

function metric(label, value, sub='') {
  return `<div class="card metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${esc(fmt(value))}</div><div class="metric-sub">${esc(sub)}</div></div>`;
}
function bars(obj, maxRows=12) {
  const entries = Object.entries(obj || {}).sort((a,b) => {
    const ai = RARITY_ORDER.indexOf(a[0]), bi = RARITY_ORDER.indexOf(b[0]);
    if (ai >= 0 && bi >= 0) return ai-bi;
    return b[1]-a[1];
  }).slice(0,maxRows);
  const max = Math.max(1,...entries.map(x => Number(x[1]) || 0));
  return `<div class="chart-bars">${entries.map(([k,v]) => `<div class="bar-row"><div>${esc(k)}</div><div class="bar-track"><div class="bar-fill" style="width:${Math.round((Number(v)||0)*100/max)}%"></div></div><div class="muted">${esc(fmt(v))}</div></div>`).join('')}</div>`;
}

async function ensureCore() {
  if (!app.meta) app.meta = await api('/api/meta');
  if (!app.dashboard) app.dashboard = await api('/api/dashboard');
  if (!app.schemas) app.schemas = await api('/api/schemas');
  updateMode();
}
function updateMode() {
  if (!app.meta) return;
  const isLive = app.meta.mode === 'live';
  modePill.className = `mode-pill ${isLive?'live':'snapshot'}`;
  if (isLive && app.meta.auth_mode === 'local-owner') {
    modePill.textContent = `LIVE • OWNER ${app.meta.admin_account || 'Local Admin'} • write ${app.meta.write_enabled ? 'ON':'OFF'}`;
  } else {
    modePill.textContent = isLive
      ? `LIVE PostgreSQL • write ${app.meta.write_enabled ? 'ON':'OFF'}`
      : `SNAPSHOT • ${app.meta.dump_started_at || 'read-only'}`;
  }
}


async function renderCommandCenter() {
  await ensureCore();
  if(!app.commandCenter) app.commandCenter=await api('/api/command-center');
  const c=app.commandCenter,d=c.dashboard||{},q=c.data_quality||{},o=c.operations||{};
  setPageMeta('Tổng quan','ADMIN / OPERATOR HOME');
  if(c.mode==='snapshot') showNotice('Đang ở SNAPSHOT read-only. Kết nối LIVE DB để thao tác.', '');
  else if(!c.write_enabled) showNotice('Đã kết nối LIVE PostgreSQL nhưng write đang khóa.', 'warning');
  else if(app.meta.auth_mode==='local-owner') showNotice(`LOCAL OWNER: ${app.meta.admin_account || 'Viet'} • thao tác trực tiếp • mọi mutation vẫn ghi audit.`, 'warning');
  else showNotice('LIVE write đang bật. Thao tác được audit.', 'warning');
  const alertCount=(Number(o.failed_outbox)||0)+(Number(o.failed_jobs)||0)+(Number(q.critical)||0)+(Number(q.high)||0);
  pageEl.innerHTML=`
    <div class="hero-command card operator-hero">
      <div><div class="eyebrow">LOST KINGSLAND ADMIN</div><h2>Operator Home</h2><p>Chỉ giữ các thao tác bạn dùng thường xuyên. Công cụ kỹ thuật sâu được ẩn trong <b>Hiện nâng cao</b>.</p></div>
      <div class="command-score ${alertCount?'warn':'good'}"><b>${alertCount}</b><span>cảnh báo</span></div>
    </div>
    <div class="grid grid-4 operator-metrics">
      ${metric('Người chơi',d.players,'Player Control')}
      ${metric('Item',d.production_equipment_defs ?? d.equipment_defs,'production catalog')}
      ${metric('Ảnh item',`${q.image_coverage_pct ?? '—'}%`,`${q.production_items_missing_image ?? '—'} thiếu ảnh`)}
      ${metric('Lỗi dữ liệu',q.issue_count ?? 0,`${q.critical ?? 0} critical`)}
    </div>
    <div class="section-head"><div><div class="section-title">Thao tác nhanh</div><div class="section-sub">Các màn hình chính để vận hành game hằng ngày.</div></div></div>
    <div class="quick-grid operator-quick-grid">
      <button data-go="players" class="card quick-card"><b>♙ Người chơi</b><span>Xem chi tiết, chỉnh progression và balance có audit</span></button>
      <button data-go="items" class="card quick-card"><b>◆ Item & Ảnh</b><span>CRUD trang bị, upload/thay/xóa artwork</span></button>
      <button data-go="characters" class="card quick-card"><b>♛ Nhân vật & Ảnh</b><span>Character catalog + artwork dùng chung Bot/Web</span></button>
      <button data-go="giftcodes" class="card quick-card"><b>🎁 Giftcode</b><span>Tạo code, reward, giới hạn và lịch sử</span></button>
      <button data-go="materials" class="card quick-card"><b>⛏ Tài nguyên & Ore</b><span>10 resource nền + 90 ore theo 9 slot × 10 phẩm chất, quản lý ảnh trực tiếp</span></button>
      <button data-go="testmedia" class="card quick-card quick-card-accent"><b>⚡ Ảnh test & Bot</b><span>Gắn ảnh placeholder hàng loạt và check pipeline Bot/Web</span></button>
      <button data-go="quality" class="card quick-card"><b>✓ Data Quality</b><span>${q.issue_count ?? 0} vấn đề cần xem</span></button>
    </div>
    <div class="grid grid-2 compact-health-grid">
      <div class="card card-pad"><div class="section-title">Hệ thống</div><div class="health-line"><span>Outbox failed</span>${statusBadge(Number(o.failed_outbox||0)===0?'SUCCEEDED':'FAILED')}</div><div class="health-line"><span>Jobs failed</span>${statusBadge(Number(o.failed_jobs||0)===0?'SUCCEEDED':'FAILED')}</div></div>
      <div class="card card-pad"><div class="section-title">Admin</div><div class="health-line"><span>Write</span>${statusBadge(c.write_enabled?'ENABLED':'DISABLED')}</div><div class="health-line"><span>Media</span><span class="badge">${esc(c.media_backend||'database')}</span></div></div>
    </div>`;
  $$('[data-go]').forEach(b=>b.onclick=()=>location.hash='#'+b.dataset.go);
}

async function renderDataQuality(){
  await ensureCore();
  app.quality=await api('/api/data-quality');
  const q=app.quality, s=q.summary||{}, issues=q.issues||[];
  setPageMeta('Data Quality','ADMIN / VALIDATION CENTER'); hideNotice();
  pageEl.innerHTML=`
    <div class="grid grid-4">${metric('Image coverage',`${s.image_coverage_pct}%`,`${s.production_items_missing_image} production item thiếu ảnh`)}${metric('Critical',s.critical,'phải xử lý trước live')}${metric('High',s.high,'schema/content integrity')}${metric('Tổng issues',s.issue_count,'automatic checks')}</div>
    <div class="toolbar"><div class="search"><input id="dqSearch" placeholder="Tìm issue, item, set…"></div><select id="dqSeverity"><option value="">Tất cả severity</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select><button id="dqRefresh" class="btn btn-secondary">↻ Re-scan</button></div>
    <div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Severity</th><th>Type</th><th>Entity</th><th>Vấn đề</th></tr></thead><tbody id="dqRows"></tbody></table></div></div>`;
  const paint=()=>{const t=$('#dqSearch').value.toLowerCase(),sev=$('#dqSeverity').value;const rows=issues.filter(x=>(!sev||x.severity===sev)&&(!t||JSON.stringify(x).toLowerCase().includes(t)));$('#dqRows').innerHTML=rows.map(x=>`<tr><td><span class="badge severity-${esc((x.severity||'').toLowerCase())}">${esc(x.severity)}</span></td><td class="code">${esc(x.type)}</td><td>${esc(x.entity)}</td><td>${esc(x.message)}${x.examples?`<div class="muted tiny">Ví dụ: ${esc(x.examples.join(', '))}</div>`:''}</td></tr>`).join('')||'<tr><td colspan="4"><div class="empty">Không có issue theo filter.</div></td></tr>';};
  $('#dqSearch').oninput=paint;$('#dqSeverity').oninput=paint;$('#dqRefresh').onclick=async()=>{app.quality=null;await renderDataQuality();};paint();
}

async function renderBulkTools(){
  await ensureCore(); setPageMeta('Bulk Tools','ADMIN / IMPORT • EXPORT • BACKUP'); hideNotice();
  const liveWrite=app.meta.mode==='live'&&app.meta.write_enabled;
  pageEl.innerHTML=`
    <div class="grid grid-3">
      <div class="card card-pad tool-card"><h3>Items CSV</h3><p class="muted">Xuất toàn bộ item definition để review/Excel.</p><a class="btn btn-primary" href="/api/export/items.csv">Tải items.csv</a></div>
      <div class="card card-pad tool-card"><h3>Config JSON</h3><p class="muted">Export tất cả resource config đang được Admin quản lý.</p><a class="btn btn-primary" href="/api/export/config.json">Tải config.json</a></div>
      <div class="card card-pad tool-card"><h3>Snapshot JSON</h3><p class="muted">Export read snapshot của toàn bộ 135-table model phục vụ backup/debug.</p><a class="btn btn-secondary" href="/api/export/snapshot.json">Tải snapshot.json</a></div>
    </div>
    <div class="section-head"><div><div class="section-title">Bulk Item Artwork từ ZIP</div><div class="section-sub">Cho tới 1000 ảnh; filename stem phải bằng item_code. Không nhập link.</div></div></div>
    <div class="card card-pad"><div id="zipDrop" class="image-drop-zone"><div class="drop-icon">ZIP</div><div class="drop-title">Chọn ZIP chứa ảnh item</div><div class="muted tiny">Ví dụ EQ_HELM_C01_COMMON.png</div><input id="zipFile" type="file" class="hidden-file" accept=".zip,application/zip"></div><div id="zipInfo" class="muted tiny">Chưa chọn ZIP.</div><div class="drawer-actions left-actions"><button id="zipUpload" class="btn btn-primary" ${liveWrite?'':'disabled'}>Upload ZIP & tự map item_code</button></div>${liveWrite?'':'<div class="inline-warning">Cần LIVE + write enabled để upload.</div>'}<div id="zipResult"></div></div>
    <div class="section-head"><div><div class="section-title">Safe bulk principle</div><div class="section-sub">Export rộng; import/write hẹp. Không có raw mass-update vào runtime player/economy/combat.</div></div></div>`;
  const drop=$('#zipDrop'),inp=$('#zipFile');drop.onclick=()=>inp.click();inp.onchange=()=>{$('#zipInfo').textContent=inp.files?.[0]?`${inp.files[0].name} • ${Math.round(inp.files[0].size/1024/1024*10)/10} MB`:'Chưa chọn ZIP.';};
  $('#zipUpload').onclick=async()=>{const f=inp.files?.[0];if(!f){alert('Chọn ZIP trước.');return;}const h=writeHeaders(false);if(!h)return;const fd=new FormData();fd.append('file',f);$('#zipUpload').disabled=true;$('#zipUpload').textContent='Đang xử lý…';try{const r=await api('/api/items/images/archive',{method:'POST',headers:h,body:fd});$('#zipResult').innerHTML=`<div class="card card-pad"><b>${r.success}/${r.total} thành công</b><div class="muted tiny">${r.failed} lỗi</div><div class="bulk-result">${r.results.slice(0,100).map(x=>`<div>${x.ok?'✓':'✕'} ${esc(x.filename)} ${x.error?`— ${esc(x.error)}`:''}</div>`).join('')}</div></div>`;app.items=null;app.dashboard=null;app.commandCenter=null;}catch(e){alert(e.message);}finally{$('#zipUpload').disabled=false;$('#zipUpload').textContent='Upload ZIP & tự map item_code';}};
}

async function renderDashboard() {
  await ensureCore();
  setPageMeta('Dashboard', 'ADMIN / OVERVIEW');
  const d = app.dashboard;
  if (app.meta.mode === 'snapshot') showNotice(`Đang chạy bản snapshot read-only từ ${app.meta.source_dump}. Không có thao tác nào ghi vào gameplay DB.`, '');
  else if (!app.meta.write_enabled) showNotice('Đang kết nối PostgreSQL thật nhưng write đang khóa. Chỉ đọc dữ liệu.', 'warning');
  else if(app.meta.auth_mode==='local-owner') showNotice(`LIVE write đang bật • Local Owner ${app.meta.admin_account || 'Viet'} • không cần ADMIN_TOKEN/xác minh • mọi mutation vẫn ghi audit.`, 'warning');
  else showNotice(`LIVE write đang bật. ${app.meta.crud_resource_count} nhóm config CRUD + Direct Item Image Upload đang hoạt động. Không nhập URL ảnh; mọi mutation đều yêu cầu ADMIN_TOKEN và ghi audit.`, 'warning');

  pageEl.innerHTML = `
    <div class="grid grid-4">
      ${metric('Người chơi', d.players, 'identity.players')}
      ${metric('Trang bị / Item defs', d.equipment_defs, `${d.production_equipment_defs ?? '—'} production + ${d.sample_equipment_defs ?? '—'} sample`)}
      ${metric('Phẩm chất', d.rarities, 'DB hiện có 10 rarity tiers')}
      ${metric('Bộ trang bị', d.equipment_sets, `${d.set_bonuses} mốc bonus 2/4/6/8`) }
      ${metric('Item đã sở hữu', d.player_item_instances, 'inventory.item_instances')}
      ${metric('Thiếu image asset', d.missing_item_images, `${d.items_with_images ?? 0} item đã có ảnh`)}
      ${metric('Media assets', d.media_assets ?? d.local_media_files ?? 0, `${d.media_backend || app.meta.media_backend || 'media'} • ảnh upload trực tiếp`)}
      ${metric('Feature flags', d.feature_flags, `${d.feature_flags_enabled} đang bật`)}
      ${metric('Abuse signals', d.abuse_signals, 'ops.abuse_signals')}
    </div>
    <div class="grid grid-2">
      <div>
        <div class="section-head"><div><div class="section-title">Phân bố rarity</div><div class="section-sub">Theo item definition trong DB</div></div></div>
        <div class="card">${bars(d.rarity_counts, 12)}</div>
      </div>
      <div>
        <div class="section-head"><div><div class="section-title">Phân bố equipment slot</div><div class="section-sub">Nguồn: inventory.item_defs</div></div></div>
        <div class="card">${bars(d.slot_counts, 12)}</div>
      </div>
    </div>
    <div class="section-head"><div><div class="section-title">Cấu trúc Admin theo GDD</div><div class="section-sub">Player Support • Game Config • Clan Ops • Economy • Discord Ops • Incident</div></div></div>
    <div class="grid grid-3">
      <div class="card card-pad"><h3>Player Support</h3><p class="muted tiny">Profile, hero, inventory, ledger và compensation.</p></div>
      <div class="card card-pad"><h3>Game Config</h3><p class="muted tiny">Regions, enemies, loot, skills, buildings, research, events.</p></div>
      <div class="card card-pad"><h3>Operations</h3><p class="muted tiny">Feature flags, audit, abuse signals, outbox, scheduled actions.</p></div>
    </div>`;
}

async function renderPlayers() {
  await ensureCore();
  if (!app.players) app.players = await api('/api/players');
  setPageMeta('Người chơi', 'ADMIN / PLAYER SUPPORT');
  hideNotice();
  pageEl.innerHTML = `
    <div class="toolbar">
      <div class="search"><input id="playerSearch" placeholder="Tìm player, hero, race, path, realm…"></div>
      <span class="muted tiny">${app.players.length} player</span>
    </div>
    <div class="card table-card"><div class="table-wrap"><table>
      <thead><tr><th>Player</th><th>Hero</th><th>Lv</th><th>Race / Path</th><th>Realm</th><th>Cultivation XP</th><th>Discord</th><th>Status</th></tr></thead>
      <tbody id="playersBody"></tbody>
    </table></div></div>`;
  const input = $('#playerSearch');
  const paint = () => {
    const q = input.value.trim().toLowerCase();
    const rows = app.players.filter(p => JSON.stringify(p).toLowerCase().includes(q));
    $('#playersBody').innerHTML = rows.map(p => `<tr class="clickable" data-player="${esc(p.player_id)}">
      <td><div class="item-name">${esc(p.player_name || p.public_display_name)}</div><div class="code">${esc(p.player_id)}</div></td>
      <td><div class="item-name">${esc(p.hero_name)}</div><div class="muted tiny">${esc(p.hero_id || '')}</div></td>
      <td>${esc(fmt(p.hero_level))}</td>
      <td>${esc(p.race_code || '—')} / ${esc(p.path_code || '—')}</td>
      <td>${esc(p.realm_code || '—')} • Tầng ${esc(fmt(p.realm_minor_stage))}</td>
      <td>${esc(fmt(p.cultivation_xp))}</td>
      <td>${esc(p.discord_username || p.discord_user_id || 'Chưa link')}</td>
      <td>${statusBadge(p.account_status || 'ACTIVE')}</td>
    </tr>`).join('') || `<tr><td colspan="8"><div class="empty">Không có kết quả.</div></td></tr>`;
    $$('tr[data-player]').forEach(tr => tr.addEventListener('click', () => openPlayer(tr.dataset.player)));
  };
  input.addEventListener('input', paint); paint();
}

async function openPlayer(playerId) {
  const p = (app.players||[]).find(x => String(x.player_id) === String(playerId));
  const [o,economyAssets] = await Promise.all([api(`/api/players/${encodeURIComponent(playerId)}/overview`), api('/api/economy/assets').catch(()=>[])]);
  const player=o.player||{}, account=(o.account||[])[0]||{}, heroes=o.heroes||[], energy=(o.energy||[])[0]||null, exploration=(o.exploration||[])[0]||null;
  const items=o.inventory_instances||o.items||[], commanders=o.commanders||[], characters=o.characters||[], kingdoms=o.kingdoms||[], buildings=o.kingdom_buildings||[], marches=o.marches||[], clans=o.clan_memberships||[], ledger=o.ledger_accounts||[];
  const liveWrite=app.meta?.mode==='live'&&app.meta?.write_enabled;
  const section=(title,rows,cols)=>`<div class="support-section"><div class="section-head"><div><div class="section-title">${esc(title)} (${rows.length})</div></div></div>${rows.length?`<div class="card table-card">${supportRowsTable(rows,cols)}</div>`:'<div class="empty compact-empty">Chưa có dữ liệu.</div>'}</div>`;
  const editSection=(title,rows,cols,target,fieldDefs)=>`<div class="support-section"><div class="section-head"><div><div class="section-title">${esc(title)} (${rows.length})</div><div class="section-sub">OWNER có thể mở từng row để chỉnh có audit.</div></div></div>${rows.length?`<div class="card table-card">${supportRowsTableEditable(rows,cols,target,playerId,fieldDefs)}</div>`:'<div class="empty compact-empty">Chưa có dữ liệu.</div>'}</div>`;
  const coreForm=(id,title,target,row,rowId,fields)=>`<div class="card card-pad player-control-card" id="${id}" data-target="${esc(target)}" data-row-id="${esc(rowId||'')}"><div class="player-control-head"><div><b>${esc(title)}</b><div class="muted tiny">Sửa trực tiếp có validation + version bump + ops.audit_logs.</div></div><button class="btn btn-primary btn-small" data-save-player-control ${liveWrite?'':'disabled'}>Lưu</button></div><div class="player-control-grid">${fields.map(f=>playerControlField(f,row?.[f.key])).join('')}</div><div class="field"><label>Reason code</label><input data-reason value="ADMIN_PLAYER_EDIT" placeholder="ADMIN_PLAYER_EDIT"></div></div>`;
  openDrawer(p?.player_name || p?.public_display_name || player.display_name || 'Player', 'PLAYER 360 / CONTROL CENTER', `
    <div class="player-console">
    <div class="player-identity-card">
      <div class="player-avatar">${esc((p?.player_name || p?.public_display_name || player.display_name || 'P').slice(0,1).toUpperCase())}</div>
      <div class="player-identity-main"><div class="player-title">${esc(p?.player_name || p?.public_display_name || player.display_name || 'Player')}</div><div class="player-id code">${esc(playerId)}</div><div class="player-chips"><span>${statusBadge(account.status || p?.account_status || 'ACTIVE')}</span><span class="chip">Lv ${esc(fmt(player.account_level ?? p?.account_level ?? 1))}</span><span class="chip">${esc(heroes[0]?.realm_code || p?.realm_code || 'No Realm')}</span></div></div>
      <div class="player-identity-stats"><div><span>Hero</span><b>${esc(heroes[0]?.name ?? p?.hero_name ?? '—')}</b></div><div><span>Hero Lv</span><b>${esc(fmt(heroes[0]?.level ?? p?.hero_level ?? 0))}</b></div><div><span>Floor</span><b>${esc(fmt(exploration?.current_floor ?? p?.current_floor ?? 0))}</b></div></div>
    </div>
    <div class="support-kpi-row">
      <div><b>${items.length}</b><span>Items</span></div><div><b>${commanders.length}</b><span>Commanders</span></div><div><b>${characters.length}</b><span>Characters</span></div><div><b>${buildings.length}</b><span>Buildings</span></div><div><b>${marches.length}</b><span>Marches</span></div><div><b>${ledger.length}</b><span>Balances</span></div>
    </div>

    <div class="support-action-card owner-control-zone">
      <div class="section-head"><div><div class="section-title">⚡ Player Control Center</div><div class="section-sub">Cho phép OWNER chỉnh số liệu người chơi. Tất cả thay đổi đều audit; số dư tiền/tài nguyên đi qua ledger operation + ledger entry, không overwrite mù.</div></div></div>
      ${liveWrite?'':'<div class="inline-warning">Cần LIVE PostgreSQL + ADMIN_WRITE_ENABLED=true.</div>'}
      <div class="grid grid-2 player-control-panels">
        ${coreForm('pcAccount','Tài khoản','account',player,playerId,[{key:'display_name',label:'Tên hiển thị'},{key:'account_level',label:'Account Level',type:'number'},{key:'account_xp',label:'Account XP',type:'number'},{key:'tutorial_step',label:'Tutorial Step'}])}
        ${account.id?coreForm('pcAccountSettings','Trạng thái tài khoản','account-settings',account,account.id,[{key:'status',label:'Status'},{key:'locale',label:'Locale'},{key:'timezone',label:'Timezone'}]):''}
        ${heroes[0]?coreForm('pcHero','Hero chính / Tu luyện','hero',heroes[0],heroes[0].id,[{key:'name',label:'Tên Hero'},{key:'level',label:'Level',type:'number'},{key:'xp',label:'XP',type:'number'},{key:'realm_code',label:'Realm'},{key:'realm_minor_stage',label:'Stage 1-10',type:'number'},{key:'cultivation_qi',label:'Linh khí',type:'number'},{key:'cultivation_progress',label:'Cultivation progress',type:'number'},{key:'tribulation_fail_streak',label:'Fail streak',type:'number'},{key:'sect_code',label:'Sect'},{key:'sect_rank',label:'Sect rank',type:'number'},{key:'sect_reputation',label:'Sect reputation',type:'number'}]):''}
        ${energy?coreForm('pcEnergy','Energy','energy',energy,playerId,[{key:'current_value',label:'Current',type:'number'},{key:'cap_value',label:'Cap',type:'number'},{key:'regen_seconds',label:'Regen seconds',type:'number'}]):''}
        ${exploration?coreForm('pcExploration','Exploration','exploration',exploration,playerId,[{key:'current_floor',label:'Current floor',type:'number'},{key:'highest_floor',label:'Highest floor',type:'number'}]):''}
      </div>
      <div class="economy-console">
        <div class="economy-console-head"><div><div class="section-title">Economy Balance Console</div><div class="section-sub">DELTA = cộng/trừ • SET = đặt số dư cuối • mọi thay đổi đều tạo ledger operation + entry + audit.</div></div><span class="badge ${app.meta?.db_permissions?.player_balance_ready?'on':'off'}">${app.meta?.db_permissions?.player_balance_ready?'DB READY':'CHECK DB PERMISSIONS'}</span></div>
        <div class="balance-any"><div class="balance-any-title"><b>Điều chỉnh Asset bất kỳ</b><span>Tự tạo ledger account nếu chưa có</span></div><div class="inline-fields"><select id="balanceAnyAsset">${(economyAssets||[]).map(a=>`<option value="${esc(a.code)}">${esc(a.code)} • ${esc(a.asset_type)}</option>`).join('')}</select><select id="balanceAnyMode"><option value="DELTA">DELTA +/-</option><option value="SET">SET TO</option></select><input id="balanceAnyAmount" type="number" step="any" placeholder="Số lượng"><input id="balanceAnyReason" value="ADMIN_BALANCE_ADJUST" placeholder="Reason code"><button id="balanceAnySave" class="btn btn-primary btn-small" ${liveWrite?'':'disabled'}>Áp dụng</button></div></div>
        <div class="balance-control-grid">${ledger.map((a,i)=>`<div class="balance-control" data-balance-index="${i}"><div class="balance-head"><div><b>${esc(a.asset_code)}</b><small>Available balance</small></div><span>${esc(fmtAmount(a.available_balance))}</span></div><div class="inline-fields"><select data-balance-mode><option value="DELTA">DELTA +/-</option><option value="SET">SET TO</option></select><input data-balance-amount type="number" step="any" placeholder="Số lượng"><input data-balance-reason value="ADMIN_BALANCE_ADJUST" placeholder="Reason code"><button class="btn btn-primary btn-small" data-balance-save ${liveWrite?'':'disabled'}>Apply</button></div></div>`).join('')||'<div class="empty compact-empty">Player chưa có ledger account; dùng dòng “Điều chỉnh Asset bất kỳ”.</div>'}</div>
      </div>
    </div>

    <details class="support-action-card player-collapsible">
      <summary><b>Support Actions</b><span>Compensation / Sanction</span></summary>
      <div class="grid grid-2 support-actions-grid player-collapsible-body">
        <div class="card card-pad"><b>Tạo Compensation Case</b><div class="field"><label>Reason code</label><input id="compReason" placeholder="INCIDENT_REWARD_REPAIR"></div><div class="grid grid-2"><div class="field"><label>Vàng</label><input id="compGold" type="number" min="0" step="1" value="1000"></div><div class="field"><label>Gem</label><input id="compGems" type="number" min="0" step="1" value="0"></div><div class="field"><label>Ngọc</label><input id="compJade" type="number" min="0" step="1" value="0"></div><div class="field"><label>Điểm kỹ năng</label><input id="compSkill" type="number" min="0" step="1" value="0"></div><div class="field"><label>Gỗ</label><input id="compWood" type="number" min="0" step="1" value="0"></div><div class="field"><label>Lương thực</label><input id="compFood" type="number" min="0" step="1" value="0"></div><div class="field"><label>Quặng</label><input id="compOre" type="number" min="0" step="1" value="0"></div><div class="field"><label>Tinh hoa</label><input id="compEssence" type="number" min="0" step="1" value="0"></div></div><button id="createComp" class="btn btn-primary" ${liveWrite?'':'disabled'}>Tạo case PENDING</button></div>
        <div class="card card-pad"><b>Tạo Sanction</b><div class="field"><label>Sanction type</label><input id="sanctionType" placeholder="CHAT_MUTE / MARKET_BLOCK / ACCOUNT_SUSPEND"></div><div class="field"><label>Reason code</label><input id="sanctionReason" placeholder="ABUSE_CONFIRMED"></div><div class="field"><label>Ends at (optional ISO)</label><input id="sanctionEnds" placeholder="2026-08-20T00:00:00+07:00"></div><button id="createSanction" class="btn btn-danger" ${liveWrite?'':'disabled'}>Tạo sanction</button></div>
      </div>
    </div>

    ${section('Discord Links',o.discord_links||[],['discord_user_id','discord_username','is_primary','linked_at','revoked_at'])}
    ${section('Hero & Cultivation (raw detail)',heroes,['id','name','level','xp','race_code','path_code','realm_code','realm_minor_stage','cultivation_qi','cultivation_progress','tribulation_fail_streak'])}
    ${editSection('Secondary Characters',characters,['display_name_vi','character_code','rarity','native_level','native_xp','ascension_rank'],'character',[{key:'native_level',label:'Native level',type:'number'},{key:'native_xp',label:'Native XP',type:'number'},{key:'ascension_rank',label:'Ascension 0-5',type:'number'},{key:'level_sync_enabled',label:'Level sync',type:'checkbox'}])}
    ${editSection('Inventory',items,['item_name','item_code','rarity','item_level','state','locked','acquired_at'],'item',[{key:'rarity',label:'Rarity'},{key:'item_level',label:'Item level',type:'number'},{key:'state',label:'State'},{key:'durability',label:'Durability',type:'number'},{key:'locked',label:'Locked',type:'checkbox'},{key:'affixes',label:'Affixes JSON',type:'json'},{key:'unique_effects',label:'Unique effects JSON',type:'json'}])}
    ${editSection('Commander',commanders,['commander_code','level','xp','star_level','status','acquired_at'],'commander',[{key:'level',label:'Level 1-5000',type:'number'},{key:'xp',label:'XP',type:'number'},{key:'star_level',label:'Star',type:'number'},{key:'status',label:'Status'}])}
    ${editSection('Kingdom Buildings',buildings,['building_code','level','updated_at'],'kingdom-building',[{key:'level',label:'Level',type:'number'},{key:'state_json',label:'State JSON',type:'json'}])}
    ${section('Kingdom Research',o.kingdom_research||[],['research_code','level','updated_at'])}
    ${section('Production Sites',o.production_sites||[],['resource_code','building_code','production_per_hour','storage_cap','stored_amount','last_accrual_at'])}
    ${section('March Slots',marches,['slot_no','status','assignment_type','commander_id','updated_at'])}
    ${section('Clan Membership',clans,['clan_name','clan_tag','rank','contribution','joined_at','last_active_at'])}
    ${section('Economy Balances',ledger,['asset_code','available_balance','reserved_balance','sequence_no'])}
    ${section('Ledger History',o.ledger_entries||[],['asset_code','delta_available','balance_before','balance_after','operation_type','reason_code','created_at'])}
    ${section('Market',o.market_listings||[],['status','listed_rarity','listed_item_level','price_asset_code','price_amount','created_at'])}
    ${section('Exploration',o.exploration||[],['current_floor','highest_floor','updated_at'])}
    ${section('Adventure Runs',o.adventure_runs||[],['region_code','status','current_node_code','started_at','completed_at'])}
    ${section('Tribulation History',o.tribulations||[],['from_realm_code','to_realm_code','final_success_chance','result','started_at','resolved_at'])}
    ${section('Sanctions',o.sanctions||[],['sanction_type','reason_code','starts_at','ends_at','revoked_at','created_by'])}
    ${section('Compensation Cases',o.compensations||[],['reason_code','status','requested_by','approved_by','created_at','resolved_at'])}
      </div>
    </details>
    </div>
  `);
  drawer.classList.add('drawer-player');

  $$('[data-save-player-control]').forEach(btn=>btn.onclick=async()=>{
    const card=btn.closest('[data-target]'); const target=card.dataset.target,rowId=card.dataset.rowId||null;
    const values={}; $$('[data-pc-field]',card).forEach(el=>{let v=el.type==='checkbox'?el.checked:el.value;if(el.dataset.kind==='number'&&v!=='')v=Number(v);values[el.dataset.pcField]=v;});
    const reason=$('[data-reason]',card)?.value||'ADMIN_PLAYER_EDIT';
    const h=writeHeaders(true);if(!h)return;
    try{await api(`/api/players/${encodeURIComponent(playerId)}/control/${encodeURIComponent(target)}${rowId?`?row_id=${encodeURIComponent(rowId)}`:''}`,{method:'PATCH',headers:h,body:JSON.stringify({values,reason_code:reason})});showNotice(`Đã cập nhật ${target} và ghi audit.`,'warning');app.players=null;await openPlayer(playerId);}catch(e){alert(e.message);}
  });
  $$('[data-balance-save]').forEach(btn=>btn.onclick=async()=>{const box=btn.closest('[data-balance-index]'),a=ledger[Number(box.dataset.balanceIndex)];const amount=$('[data-balance-amount]',box).value;if(amount===''){alert('Nhập amount.');return;}const h=writeHeaders(true);if(!h)return;try{await api(`/api/players/${encodeURIComponent(playerId)}/balance-adjust`,{method:'POST',headers:h,body:JSON.stringify({asset_code:a.asset_code,mode:$('[data-balance-mode]',box).value,amount,reason_code:$('[data-balance-reason]',box).value||'ADMIN_BALANCE_ADJUST'})});showNotice(`Đã điều chỉnh ${a.asset_code} có ledger entry.`,'warning');await openPlayer(playerId);}catch(e){alert(e.message);}});
  const balanceAny=$('#balanceAnySave'); if(balanceAny)balanceAny.onclick=async()=>{const asset=$('#balanceAnyAsset').value,amount=$('#balanceAnyAmount').value;if(!asset||amount===''){alert('Chọn asset và nhập amount.');return;}const h=writeHeaders(true);if(!h)return;try{await api(`/api/players/${encodeURIComponent(playerId)}/balance-adjust`,{method:'POST',headers:h,body:JSON.stringify({asset_code:asset,mode:$('#balanceAnyMode').value,amount,reason_code:$('#balanceAnyReason').value||'ADMIN_BALANCE_ADJUST'})});showNotice(`Đã điều chỉnh ${asset} có ledger entry.`,'warning');await openPlayer(playerId);}catch(e){alert(e.message);}};
  $$('[data-player-row-edit]').forEach(btn=>btn.onclick=()=>{const target=btn.dataset.playerRowEdit, idx=Number(btn.dataset.rowIndex); const map={character:characters,item:items,commander:commanders,'kingdom-building':buildings}; const row=(map[target]||[])[idx]; const defs=JSON.parse(btn.dataset.fieldDefs||'[]'); openPlayerRowEditor(playerId,target,row,defs);});
  const compBtn=$('#createComp'); if(compBtn)compBtn.onclick=async()=>{const h=writeHeaders(true);if(!h)return;const bundle={};for(const [code,id] of [['GOLD','compGold'],['GEMS','compGems'],['JADE','compJade'],['SKILL_POINT','compSkill'],['WOOD','compWood'],['FOOD','compFood'],['ORE','compOre'],['ESSENCE','compEssence']]){const n=Number($('#'+id).value||0);if(!Number.isSafeInteger(n)||n<0){alert('Phần thưởng phải là số nguyên không âm.');return;}if(n>0)bundle[code]=n;}const reason=$('#compReason').value.trim();if(!reason){alert('Nhập reason code.');return;}if(!Object.keys(bundle).length){alert('Cần ít nhất một phần thưởng.');return;}try{await api(`/api/support/players/${encodeURIComponent(playerId)}/compensation`,{method:'POST',headers:h,body:JSON.stringify({reason_code:reason,reward_bundle:bundle,evidence_json:{source:'ADMIN_PLAYER_360'}})});showNotice('Đã tạo compensation case PENDING; chưa grant reward.','warning');closeDrawer();await openPlayer(playerId);}catch(e){alert(e.message);}};
  const sancBtn=$('#createSanction'); if(sancBtn)sancBtn.onclick=async()=>{const h=writeHeaders(true);if(!h)return;const sanction_type=$('#sanctionType').value.trim(),reason_code=$('#sanctionReason').value.trim(),ends_at=$('#sanctionEnds').value.trim()||null;if(!sanction_type||!reason_code){alert('Nhập sanction type và reason code.');return;}if(!confirm(`Tạo sanction ${sanction_type} cho player này?`))return;try{await api(`/api/support/players/${encodeURIComponent(playerId)}/sanctions`,{method:'POST',headers:h,body:JSON.stringify({sanction_type,reason_code,ends_at,evidence_json:{source:'ADMIN_PLAYER_360'}})});showNotice('Đã tạo sanction và ghi audit.','warning');closeDrawer();await openPlayer(playerId);}catch(e){alert(e.message);}};
}

function playerControlField(def,value){
  const type=def.type||'text', key=def.key;
  if(type==='checkbox') return `<div class="field checkbox-field"><label>${esc(def.label)}</label><input data-pc-field="${esc(key)}" type="checkbox" ${value?'checked':''}></div>`;
  const val=type==='json'?JSON.stringify(value??{},null,2):(value??'');
  if(type==='json') return `<div class="field span-2"><label>${esc(def.label)}</label><textarea data-pc-field="${esc(key)}" data-kind="json">${esc(val)}</textarea></div>`;
  return `<div class="field"><label>${esc(def.label)}</label><input data-pc-field="${esc(key)}" data-kind="${type==='number'?'number':'text'}" type="${type==='number'?'number':'text'}" value="${esc(val)}"></div>`;
}

function supportRowsTableEditable(rows, preferredCols, target, playerId, fieldDefs){
  const all=[...new Set(rows.flatMap(r=>Object.keys(r)))]; const cols=[...preferredCols.filter(c=>all.includes(c)),...all.filter(c=>!preferredCols.includes(c))].slice(0,7);
  const defs=esc(JSON.stringify(fieldDefs));
  return `<div class="table-wrap"><table><thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}<th></th></tr></thead><tbody>${rows.map((r,i)=>`<tr>${cols.map(c=>`<td title="${esc(fmt(r[c]))}">${esc(trunc(r[c],42))}</td>`).join('')}<td><button class="btn btn-secondary btn-small" data-player-row-edit="${esc(target)}" data-row-index="${i}" data-field-defs="${defs}">Sửa</button></td></tr>`).join('')}</tbody></table></div>`;
}

function openPlayerRowEditor(playerId,target,row,fieldDefs){
  const rowId=row.id||row.player_id;
  openDrawer(`Sửa ${target}`,'PLAYER CONTROL / ROW EDIT',`<div class="inline-warning">Đây là runtime state. Admin sẽ validate, bump version nếu có và ghi ops.audit_logs.</div><div class="card card-pad"><div class="player-control-grid">${fieldDefs.map(f=>playerControlField(f,row[f.key])).join('')}</div><div class="field"><label>Reason code</label><input id="rowEditReason" value="ADMIN_PLAYER_EDIT"></div><div class="drawer-actions"><button id="rowEditBack" class="btn btn-secondary">← Player 360</button><button id="rowEditSave" class="btn btn-primary">Lưu thay đổi</button></div></div>`);
  $('#rowEditBack').onclick=()=>openPlayer(playerId);
  $('#rowEditSave').onclick=async()=>{const values={}; $$('[data-pc-field]',$('#drawerBody')).forEach(el=>{let v=el.type==='checkbox'?el.checked:el.value;if(el.dataset.kind==='number'&&v!=='')v=Number(v);values[el.dataset.pcField]=v;});const h=writeHeaders(true);if(!h)return;try{await api(`/api/players/${encodeURIComponent(playerId)}/control/${encodeURIComponent(target)}?row_id=${encodeURIComponent(rowId)}`,{method:'PATCH',headers:h,body:JSON.stringify({values,reason_code:$('#rowEditReason').value||'ADMIN_PLAYER_EDIT'})});showNotice(`Đã sửa ${target}.`,'warning');await openPlayer(playerId);}catch(e){alert(e.message);}};
}

function supportRowsTable(rows, preferredCols=[]) {
  const all=[...new Set(rows.flatMap(r=>Object.keys(r)))];
  const cols=[...preferredCols.filter(c=>all.includes(c)),...all.filter(c=>!preferredCols.includes(c))].slice(0,8);
  return `<div class="table-wrap"><table><thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${cols.map(c=>`<td title="${esc(fmt(r[c]))}">${esc(trunc(r[c],52))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function detail(label, value) {
  return `<div class="detail-box"><div class="detail-label">${esc(label)}</div><div class="detail-value">${esc(fmt(value))}</div></div>`;
}

async function renderItems() {
  await ensureCore();
  if (!app.items) app.items = await api('/api/items');
  setPageMeta('Trang bị & Item', 'ADMIN / GAME CONFIG');
  hideNotice();
  app.page = 1;
  pageEl.innerHTML = `
    <div class="toolbar">
      <div class="search"><input id="itemSearch" placeholder="Tìm tên, code, set, tag…"></div>
      <select id="rarityFilter"><option value="">Tất cả rarity</option>${RARITY_ORDER.map(r => `<option>${r}</option>`).join('')}</select>
      <select id="slotFilter"><option value="">Tất cả slot</option>${[...new Set(app.items.map(x=>x.equipment_slot).filter(Boolean))].sort().map(r => `<option>${esc(r)}</option>`).join('')}</select>
      <select id="imageFilter"><option value="">Ảnh: tất cả</option><option value="missing">Chưa có ảnh</option><option value="has">Đã có ảnh</option></select>
      <select id="kindFilter"><option value="production" selected>Production (480)</option><option value="sample">Sample / balance</option><option value="">Tất cả</option></select>
      <button id="bulkImageBtn" class="btn btn-secondary">▣ Upload nhiều ảnh</button>
      <button id="createItemBtn" class="btn btn-primary">＋ Tạo Item</button>
    </div>
    <div class="card card-pad item-help"><b>Ảnh Item SUPER MEGA v4:</b> kéo-thả hoặc chọn file trực tiếp từ máy. Không có ô nhập link/URL. Tên file bulk = đúng <span class="code">item_code</span> (ví dụ <span class="code">EQ_HELM_C01_COMMON.png</span>).</div>
    <div id="itemTable"></div>`;
  ['#itemSearch','#rarityFilter','#slotFilter','#imageFilter','#kindFilter'].forEach(sel => $(sel).addEventListener('input', () => {app.page=1; paintItems();}));
  $('#createItemBtn').onclick=()=>openCrudCreate('item-defs');
  $('#bulkImageBtn').onclick=()=>openBulkImageUpload();
  paintItems();
}

function filteredItems() {
  const q = $('#itemSearch')?.value.trim().toLowerCase() || '';
  const rarity = $('#rarityFilter')?.value || '';
  const slot = $('#slotFilter')?.value || '';
  const image = $('#imageFilter')?.value || '';
  const kind = $('#kindFilter')?.value || '';
  return app.items.filter(i => {
    const isSample = String(i.item_code || '').toUpperCase().includes('SAMPLE');
    if (kind === 'production' && isSample) return false;
    if (kind === 'sample' && !isSample) return false;
    if (rarity && i.rarity !== rarity) return false;
    if (slot && i.equipment_slot !== slot) return false;
    if (image === 'missing' && i.image_asset_key) return false;
    if (image === 'has' && !i.image_asset_key) return false;
    if (q && !JSON.stringify([i.item_code,i.item_name,i.set_name,i.tags,i.affix_combo_code]).toLowerCase().includes(q)) return false;
    return true;
  });
}
function paintItems() {
  const rows = filteredItems();
  const pages = Math.max(1, Math.ceil(rows.length / app.pageSize));
  app.page = Math.min(app.page, pages);
  const start = (app.page-1)*app.pageSize;
  const slice = rows.slice(start,start+app.pageSize);
  $('#itemTable').innerHTML = `<div class="card table-card"><div class="table-wrap"><table>
    <thead><tr><th>Item</th><th>Rarity</th><th>Slot</th><th>Set</th><th>Stat combo</th><th>Image</th><th>Transfer</th></tr></thead>
    <tbody>${slice.map(i => `<tr class="clickable" data-item="${esc(i.item_def_id)}">
      <td><div class="item-cell">${itemIcon(i)}<div><div class="item-name">${esc(i.item_name || 'Chưa đặt tên')}</div><div class="code">${esc(i.item_code)}</div></div></div></td>
      <td>${rarityBadge(i.rarity)}</td><td>${esc(i.equipment_slot || '—')}</td>
      <td>${esc(i.set_name || 'LẺ')}</td>
      <td><div class="chips">${(i.allowed_stat_combination || []).slice(0,4).map(x=>`<span class="chip">${esc(x)}</span>`).join('') || '<span class="muted">—</span>'}</div></td>
      <td>${i.image_url ? `<div class="image-status-cell"><img src="${esc(i.image_url)}?t=${Date.now()}" alt=""><span class="badge on">Đã có ảnh</span></div>` : '<span class="badge off">Chưa có ảnh</span>'}</td>
      <td>${i.transferable ? '<span class="badge on">Yes</span>' : '<span class="badge off">No</span>'}</td>
    </tr>`).join('') || `<tr><td colspan="7"><div class="empty">Không có kết quả.</div></td></tr>`}</tbody>
  </table></div><div class="pagination"><span>${rows.length} item • trang ${app.page}/${pages}</span><div class="pager-actions"><button id="prevPage" class="btn btn-secondary btn-small">←</button><button id="nextPage" class="btn btn-secondary btn-small">→</button></div></div></div>`;
  $$('tr[data-item]').forEach(tr => tr.addEventListener('click', () => openItem(tr.dataset.item)));
  $('#prevPage').onclick = () => { if (app.page>1) {app.page--;paintItems();} };
  $('#nextPage').onclick = () => { if (app.page<pages) {app.page++;paintItems();} };
}

function parseJsonField(text, label) {
  try { return JSON.parse(text); }
  catch { throw new Error(`${label} không phải JSON hợp lệ.`); }
}
function isLocalOwnerMode() {
  return app.meta?.auth_mode === 'local-owner';
}
function getAdminToken() {
  if (isLocalOwnerMode()) return '';
  let token = sessionStorage.getItem('lk_admin_token') || '';
  if (!token && app.meta?.mode === 'live' && app.meta?.write_enabled) {
    token = prompt('Nhập ADMIN_TOKEN cho live write:') || '';
    if (token) sessionStorage.setItem('lk_admin_token', token);
  }
  return token;
}
function getAdminActor() {
  if (isLocalOwnerMode()) return app.meta?.admin_account || 'Viet';
  let actor = sessionStorage.getItem('lk_admin_actor') || '';
  if (!actor) {
    actor = prompt('Tên người thao tác để ghi Audit (ví dụ Viet):', 'Viet') || 'local-admin';
    sessionStorage.setItem('lk_admin_actor', actor);
  }
  return actor;
}
function writeHeaders(json=true) {
  const h={'X-Admin-Actor':getAdminActor()};
  if (!isLocalOwnerMode()) {
    const token=getAdminToken();
    if (!token) return null;
    h['X-Admin-Token']=token;
  }
  if (json) h['Content-Type']='application/json';
  return h;
}
function imagePreview(item) {
  if (!item.image_url) return `<div class="image-empty image-empty-large"><div class="image-empty-icon">＋</div><div>Chưa có artwork</div><div class="muted tiny">Chọn file ảnh bên dưới để thêm trực tiếp</div></div>`;
  return `<div class="image-preview"><img src="${esc(item.image_url)}?t=${Date.now()}" alt="${esc(item.item_name||item.item_code)}"><div class="image-caption">Artwork hiện tại • upload trực tiếp từ Admin</div></div>`;
}

function previewSelectedImage(file) {
  if (!file) return;
  const url=URL.createObjectURL(file);
  const p=$('#selectedImagePreview');
  if(p){p.innerHTML=`<img src="${url}" alt="preview"><div><b>${esc(file.name)}</b><div class="muted tiny">${fmt(Math.round(file.size/1024))} KB • sẽ chuẩn hóa sang WebP</div></div>`;}
  setTimeout(()=>URL.revokeObjectURL(url),30000);
}

function wireDirectImageDrop() {
  const drop=$('#imageDropZone'), input=$('#itemImageFile');
  if(!drop||!input)return;
  drop.onclick=(e)=>{ if(e.target.closest('button'))return; input.click(); };
  input.onchange=()=>previewSelectedImage(input.files?.[0]);
  ['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('dragover');}));
  ['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('dragover');}));
  drop.addEventListener('drop',e=>{
    const files=e.dataTransfer?.files; if(!files?.length)return;
    const dt=new DataTransfer(); dt.items.add(files[0]); input.files=dt.files; previewSelectedImage(files[0]);
  });
}

function openBulkImageUpload() {
  const liveWrite=app.meta?.mode==='live'&&app.meta?.write_enabled;
  openDrawer('Upload nhiều ảnh Item','DIRECT MEDIA UPLOAD',`
    <div class="bulk-upload-intro"><b>Tối đa 500 ảnh/lần.</b><br>Tên file phải bằng đúng <span class="code">item_code</span>. Ví dụ: <span class="code">EQ_WEAPON_C03_GOD.png</span>.</div>
    <div id="bulkDropZone" class="image-drop-zone bulk-drop-zone">
      <div class="drop-icon">▣</div><div class="drop-title">Kéo nhiều ảnh vào đây</div><div class="muted">hoặc bấm để chọn file từ máy</div>
      <input id="bulkImageFiles" class="hidden-file" type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif">
    </div>
    <div id="bulkSelected" class="selected-files muted tiny">Chưa chọn file.</div>
    <div class="drawer-actions"><button id="bulkUploadNow" class="btn btn-primary" ${liveWrite?'':'disabled'}>Upload & tự gắn vào Item</button></div>
    ${liveWrite?'':'<div class="inline-warning">Cần PostgreSQL LIVE + ADMIN_WRITE_ENABLED=true để gắn ảnh vào item_defs.</div>'}
  `);
  const drop=$('#bulkDropZone'), input=$('#bulkImageFiles'), selected=$('#bulkSelected');
  const paint=()=>{const fs=[...(input.files||[])];selected.innerHTML=fs.length?`<b>${fs.length} file</b><br>${fs.slice(0,20).map(f=>esc(f.name)).join('<br>')}${fs.length>20?`<br>… +${fs.length-20} file`:''}`:'Chưa chọn file.';};
  drop.onclick=()=>input.click(); input.onchange=paint;
  ['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('dragover');}));
  ['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('dragover');}));
  drop.addEventListener('drop',e=>{const fs=e.dataTransfer?.files;if(!fs?.length)return;const dt=new DataTransfer();[...fs].slice(0,500).forEach(f=>dt.items.add(f));input.files=dt.files;paint();});
  $('#bulkUploadNow').onclick=async()=>{
    const fs=[...(input.files||[])];if(!fs.length){alert('Chọn ít nhất 1 ảnh.');return;}
    const headers=writeHeaders(false);if(!headers)return;
    const fd=new FormData();fs.forEach(f=>fd.append('files',f));
    $('#bulkUploadNow').disabled=true;$('#bulkUploadNow').textContent='Đang upload…';
    try{const r=await api('/api/items/images/bulk',{method:'POST',headers,body:fd});
      selected.innerHTML=`<b>Hoàn tất: ${r.success}/${r.total}</b><br>${r.results.map(x=>`${x.ok?'✓':'✕'} ${esc(x.filename)}${x.error?` — ${esc(x.error)}`:''}`).join('<br>')}`;
      app.items=null;app.dashboard=null;app.tableCache.clear();showNotice(`Bulk image: ${r.success} thành công, ${r.failed} lỗi.` , r.failed?'warning':'');
    }catch(e){alert(e.message);}finally{$('#bulkUploadNow').disabled=false;$('#bulkUploadNow').textContent='Upload & tự gắn vào Item';}
  };
}

async function loadItemGallery(item){
  const box=$('#itemGalleryPanel'); if(!box)return;
  try{
    const g=await api(`/api/items/${encodeURIComponent(item.item_def_id)}/gallery`), rows=g.rows||[];
    box.innerHTML=`
      <div class="section-head"><div><div class="section-title">Media Gallery</div><div class="section-sub">Nhiều ảnh cho cùng Item: PRIMARY / DISCORD / DETAIL / THUMBNAIL / GALLERY. Bot vẫn dùng PRIMARY qua image_asset_key.</div></div></div>
      ${g.gallery_enabled?`<div class="gallery-grid">${rows.map(r=>`<div class="gallery-card ${r.is_primary?'primary':''}"><img src="${esc(r.url)}?t=${Date.now()}" alt=""><div><b>${esc(r.media_role||'GALLERY')}</b><div class="muted tiny">${r.width||'—'}×${r.height||'—'} • ${r.size_bytes?Math.round(r.size_bytes/1024)+' KB':'—'}</div></div><div class="gallery-actions">${r.is_primary?'<span class="badge on">PRIMARY</span>':`<button class="btn btn-secondary btn-small" data-primary="${esc(r.asset_key)}">Đặt Primary</button><button class="btn btn-danger btn-small" data-gallery-delete="${esc(r.asset_key)}">Xóa</button>`}</div></div>`).join('')||'<div class="empty compact-empty">Chưa có gallery image.</div>'}</div>
      <div class="gallery-upload-row"><select id="galleryRole"><option>GALLERY</option><option>DISCORD</option><option>DETAIL</option><option>THUMBNAIL</option></select><input id="galleryFile" type="file" accept="image/png,image/jpeg,image/webp,image/gif"><button id="galleryUpload" class="btn btn-primary" ${app.meta.mode==='live'&&app.meta.write_enabled?'':'disabled'}>＋ Thêm ảnh Gallery</button></div>`:`<div class="inline-warning">Gallery nhiều ảnh chưa bật. Chạy <span class="code">sql/32_entity_media_links.sql</span>. Ảnh PRIMARY trực tiếp bên trên vẫn dùng bình thường.</div>`}`;
    if(!g.gallery_enabled)return;
    $$('[data-primary]',box).forEach(b=>b.onclick=async()=>{const h=writeHeaders(true);if(!h)return;try{await api(`/api/items/${encodeURIComponent(item.item_def_id)}/gallery/primary`,{method:'POST',headers:h,body:JSON.stringify({asset_key:b.dataset.primary})});app.items=null;app.dashboard=null;app.commandCenter=null;await loadItemGallery(item);showNotice(`Đã đổi PRIMARY image của ${item.item_code}. Discord bot sẽ dùng ảnh mới.`,'warning');}catch(e){alert(e.message);}});
    $$('[data-gallery-delete]',box).forEach(b=>b.onclick=async()=>{if(!confirm('Xóa ảnh gallery này?'))return;const h=writeHeaders(false);if(!h)return;try{await api(`/api/items/${encodeURIComponent(item.item_def_id)}/gallery?asset_key=${encodeURIComponent(b.dataset.galleryDelete)}`,{method:'DELETE',headers:h});await loadItemGallery(item);}catch(e){alert(e.message);}});
    const up=$('#galleryUpload');if(up)up.onclick=async()=>{const f=$('#galleryFile').files?.[0];if(!f){alert('Chọn ảnh gallery trước.');return;}const h=writeHeaders(false);if(!h)return;const fd=new FormData();fd.append('file',f);try{await api(`/api/items/${encodeURIComponent(item.item_def_id)}/gallery?role=${encodeURIComponent($('#galleryRole').value)}`,{method:'POST',headers:h,body:fd});await loadItemGallery(item);}catch(e){alert(e.message);}};
  }catch(e){box.innerHTML=`<div class="inline-warning">Không tải được gallery: ${esc(e.message)}</div>`;}
}

function openItem(itemId) {
  const item = app.items.find(x => String(x.item_def_id) === String(itemId));
  if (!item) return;
  const staged = getStaged()[item.item_def_id]?.patch || {};
  const merged = {...item, ...staged};
  const liveWrite = app.meta.mode==='live' && app.meta.write_enabled;
  openDrawer(item.item_name || item.item_code, 'ITEM DEFINITION + MEDIA', `
    ${imagePreview(item)}
    <div class="detail-grid">
      ${detail('Item ID', item.item_def_id)} ${detail('Code', item.item_code)}
      ${detail('Config', item.config_version)} ${detail('Rarity', item.rarity)}
      ${detail('Slot', item.equipment_slot)} ${detail('Set', item.set_name || 'LẺ')}
      ${detail('Affix combo', item.affix_combo_code)} ${detail('Artwork', item.image_url ? 'Đã upload' : 'Chưa có')}
    </div>

    <div class="section-head"><div><div class="section-title">Artwork / Media</div><div class="section-sub">Thêm ảnh trực tiếp từ máy. Không có ô URL/link. Admin tự lưu binary và gắn asset nội bộ cho Item; Discord Bot không cần copy ảnh vào folder gameplay.</div></div></div>
    <div class="media-upload-box direct-media-box">
      <div id="imageDropZone" class="image-drop-zone">
        <div class="drop-icon">⇧</div>
        <div class="drop-title">Kéo ảnh vào đây hoặc bấm để chọn file</div>
        <div class="muted tiny">PNG / JPEG / WebP / GIF • tối đa ${esc(app.meta.max_image_mb || 10)} MB • tự chuẩn hóa WebP</div>
        <input id="itemImageFile" class="hidden-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif">
      </div>
      <div id="selectedImagePreview" class="selected-image-preview"><span class="muted tiny">Chưa chọn ảnh mới.</span></div>
      <div class="drawer-actions left-actions">
        <button id="uploadImageBtn" class="btn btn-primary" ${liveWrite?'':'disabled'}>${item.image_asset_key?'↻ Thay ảnh bằng file đã chọn':'＋ Upload ảnh vào Item'}</button>
        <button id="deleteImageBtn" class="btn btn-danger" ${liveWrite&&item.image_asset_key?'':'disabled'}>Xóa ảnh hiện tại</button>
      </div>
      <div class="media-contract"><b>Đồng bộ Bot:</b> bot có thể lấy binary theo <span class="code">item_code</span> từ shared DB/media resolver; không cần biết tên file hay đường dẫn của Admin.</div>
      ${liveWrite?'':'<div class="inline-warning">Đang snapshot/read-only. Muốn upload ảnh và bot nhận ngay: kết nối PostgreSQL LIVE + bật ADMIN_WRITE_ENABLED=true.</div>'}
    </div>
    <div id="itemGalleryPanel" class="item-gallery-panel"><div class="empty compact-empty">Đang tải Media Gallery…</div></div>

    <div class="section-head"><div><div class="section-title">Item fields</div><div class="section-sub">Có thể sửa trực tiếp khi LIVE write bật; snapshot vẫn stage/export SQL như bản cũ.</div></div></div>
    <div class="form-grid" id="itemForm">
      <div class="field full"><label>Tên hiển thị VI</label><input id="fName" value="${esc(merged.display_name_vi ?? merged.item_name ?? '')}"></div>
      <div class="field"><label>Item type</label><input id="fItemType" value="${esc(merged.item_type || '')}"></div>
      <div class="field"><label>Family code</label><input id="fFamily" value="${esc(merged.family_code || '')}"></div>
      <div class="field"><label>Equipment slot</label><input id="fSlot" value="${esc(merged.equipment_slot || '')}"></div>
      <div class="field"><label>Rarity</label><select id="fRarity">${RARITY_ORDER.map(r=>`<option ${r===merged.rarity?'selected':''}>${r}</option>`).join('')}</select></div>
      <div class="field"><label>Transferable</label><select id="fTransfer"><option value="true" ${merged.transferable?'selected':''}>true</option><option value="false" ${!merged.transferable?'selected':''}>false</option></select></div>
      <div class="field"><label>Stackable</label><select id="fStackable"><option value="false" ${!merged.stackable?'selected':''}>false</option><option value="true" ${merged.stackable?'selected':''}>true</option></select></div>
      <div class="field"><label>Max stack</label><input id="fMaxStack" type="number" value="${esc(merged.max_stack ?? '')}"></div>
      <div class="field"><label>Bind rule</label><input id="fBind" value="${esc(merged.bind_rule || 'ACCOUNT')}"></div>
      <div class="field full"><label>Tags (phân cách dấu phẩy)</label><input id="fTags" value="${esc((merged.tags || []).join ? (merged.tags || []).join(', ') : merged.tags || '')}"></div>
      <div class="field"><label>Affix combo code</label><input id="fAffix" value="${esc(merged.affix_combo_code || '')}"></div>
      <div class="field"><label>Set code</label><input id="fSetCode" value="${esc(merged.set_code || '')}"></div>
      <div class="field full"><label>Set name</label><input id="fSetName" value="${esc(merged.set_name || '')}"></div>
      <div class="field full"><label>Base stats (JSON)</label><textarea id="fStats">${esc(JSON.stringify(merged.base_stats || {}, null, 2))}</textarea></div>
      <div class="field full"><label>Base effects (JSON)</label><textarea id="fEffects">${esc(JSON.stringify(merged.base_effects || [], null, 2))}</textarea></div>
      <div class="field full"><label>Salvage rule (JSON)</label><textarea id="fSalvage">${esc(JSON.stringify(merged.salvage_rule || {}, null, 2))}</textarea></div>
    </div>
    <div class="drawer-actions"><button id="stageBtn" class="btn btn-secondary">Stage local</button><button id="saveLiveBtn" class="btn btn-primary">${liveWrite?'Lưu LIVE':'Stage & xuất SQL'}</button><button id="deleteItemBtn" class="btn btn-danger" ${liveWrite?'':'disabled'}>Xóa Item</button></div>
    <div class="section-head"><div><div class="section-title">Set identity</div></div></div>
    <div class="json">${esc(item.set_identity || 'Không thuộc set.')}</div>
  `);
  wireDirectImageDrop();
  loadItemGallery(item);
  const collect = () => ({
    display_name_vi: $('#fName').value.trim() || null,
    item_type: $('#fItemType').value.trim(),
    family_code: $('#fFamily').value.trim() || null,
    equipment_slot: $('#fSlot').value.trim() || null,
    rarity: $('#fRarity').value,
    transferable: $('#fTransfer').value === 'true',
    stackable: $('#fStackable').value === 'true',
    max_stack: $('#fMaxStack').value === '' ? null : Number($('#fMaxStack').value),
    bind_rule: $('#fBind').value.trim() || 'ACCOUNT',
    tags: $('#fTags').value.split(',').map(x=>x.trim()).filter(Boolean),
    affix_combo_code: $('#fAffix').value.trim() || null,
    set_code: $('#fSetCode').value.trim() || null,
    set_name: $('#fSetName').value.trim() || null,
    base_stats: parseJsonField($('#fStats').value, 'Base stats'),
    base_effects: parseJsonField($('#fEffects').value, 'Base effects'),
    salvage_rule: parseJsonField($('#fSalvage').value, 'Salvage rule'),
  });
  $('#stageBtn').onclick = () => {
    try { const patch = collect(); stageItem(item, patch); showNotice(`Đã stage ${item.item_code}. Chưa ghi vào DB.`, ''); closeDrawer(); if(app.route==='staged') renderStaged(); }
    catch(e){ alert(e.message); }
  };
  $('#saveLiveBtn').onclick = async () => {
    let patch;
    try { patch = collect(); } catch(e){ alert(e.message); return; }
    if (liveWrite) {
      const headers=writeHeaders(true); if(!headers)return;
      try {
        await api(`/api/items/${encodeURIComponent(item.item_def_id)}`, {method:'PATCH',headers,body:JSON.stringify(patch)});
        app.items = null; app.dashboard = null; app.tableCache.clear();
        showNotice(`Đã cập nhật LIVE ${item.item_code}.`, 'warning'); closeDrawer(); await renderItems();
      } catch(e) { alert(e.message); }
    } else {
      stageItem(item, patch); closeDrawer(); showNotice(`Đã stage ${item.item_code}. Hãy review và xuất SQL trước khi áp vào DB.`, '');
    }
  };
  $('#uploadImageBtn').onclick = async () => {
    const file=$('#itemImageFile').files?.[0];
    if(!file){alert('Chọn file ảnh trước.');return;}
    const headers=writeHeaders(false); if(!headers)return;
    const fd=new FormData(); fd.append('file',file);
    try {
      const result=await api(`/api/items/${encodeURIComponent(item.item_def_id)}/image`,{method:'POST',headers,body:fd});
      app.items=null; app.dashboard=null; app.tableCache.clear();
      showNotice(`Đã ${item.image_asset_key?'thay':'thêm'} ảnh trực tiếp cho ${item.item_code}. Media backend: ${result.media_backend}.`, 'warning');
      closeDrawer(); await renderItems();
    } catch(e){alert(e.message);}
  };
  $('#deleteImageBtn').onclick = async () => {
    if(!confirm(`Xóa ảnh hiện tại của ${item.item_code}?`))return;
    const headers=writeHeaders(false); if(!headers)return;
    try {
      await api(`/api/items/${encodeURIComponent(item.item_def_id)}/image`,{method:'DELETE',headers});
      app.items=null; app.dashboard=null; app.tableCache.clear();
      showNotice(`Đã xóa ảnh của ${item.item_code}. Bot sẽ nhận trạng thái không có ảnh.`, 'warning'); closeDrawer(); await renderItems();
    } catch(e){alert(e.message);}
  };
  $('#deleteItemBtn').onclick = async () => {
    if(!confirm(`XÓA item definition ${item.item_code}? DB sẽ chặn nếu item đang được gameplay row tham chiếu.`))return;
    const headers=writeHeaders(false); if(!headers)return;
    const pk=encodeURIComponent(JSON.stringify({id:item.item_def_id}));
    try {
      await api(`/api/crud/item-defs?pk=${pk}`,{method:'DELETE',headers});
      app.items=null; app.dashboard=null; app.tableCache.clear(); closeDrawer(); showNotice(`Đã xóa item ${item.item_code}.`,'warning'); await renderItems();
    } catch(e){alert(e.message);}
  };
}

async function renderSets() {
  await ensureCore();
  if (!app.sets) app.sets = await api('/api/sets');
  setPageMeta('Bộ trang bị', 'ADMIN / GAME CONFIG'); hideNotice();
  pageEl.innerHTML = `<div class="toolbar"><div class="search"><input id="setSearch" placeholder="Tìm set, rarity, identity…"></div><select id="setRarity"><option value="">Tất cả rarity</option>${RARITY_ORDER.map(r=>`<option>${r}</option>`).join('')}</select></div><div id="setGrid" class="set-grid"></div>`;
  const paint = () => {
    const q=$('#setSearch').value.toLowerCase(), r=$('#setRarity').value;
    const sets=app.sets.filter(s=>(!r||s.rarity===r)&&(!q||JSON.stringify(s).toLowerCase().includes(q)));
    $('#setGrid').innerHTML=sets.map(s=>`<div class="card set-card">
      <div class="set-head"><div><div class="set-name">${esc(s.set_name)}</div><div class="code">${esc(s.set_code)}</div></div>${rarityBadge(s.rarity)}</div>
      <div class="set-desc">${esc(s.identity_summary || '')}</div>
      <div class="bonus-list">${(s.bonuses||[]).map(b=>`<button class="bonus bonus-button" data-bonus-set="${esc(s.set_code)}" data-bonus-pieces="${esc(b.pieces_required)}"><div class="bonus-k">${esc(b.pieces_required)} MÓN</div><div class="bonus-v">${esc(b.display_text_vi || b.bonus_type)}</div></button>`).join('')}</div>
      <div class="resource-card-actions set-actions"><button class="btn btn-secondary btn-small" data-edit-set="${esc(s.set_code)}">Sửa Set</button><button class="btn btn-primary btn-small" data-create-bonus="${esc(s.set_code)}" ${app.meta.mode==='live'&&app.meta.write_enabled?'':'disabled'}>＋ Bonus</button></div>
    </div>`).join('') || `<div class="card empty">Không có kết quả.</div>`;
    $$('[data-edit-set]').forEach(b=>b.onclick=async()=>{try{const d=await api('/api/crud/equipment-sets?limit=1000');const row=(d.rows||[]).find(x=>x.set_code===b.dataset.editSet);if(row)openCrudEditor('equipment-sets',row);else alert('Không tìm thấy raw set row.');}catch(e){alert(e.message);}});
    $$('[data-bonus-set]').forEach(b=>b.onclick=async()=>{try{const d=await api('/api/crud/set-bonuses?limit=1000');const row=(d.rows||[]).find(x=>x.set_code===b.dataset.bonusSet&&String(x.pieces_required)===String(b.dataset.bonusPieces));if(row)openCrudEditor('set-bonuses',row);else alert('Không tìm thấy raw bonus row.');}catch(e){alert(e.message);}});
    $$('[data-create-bonus]').forEach(b=>b.onclick=()=>openCrudCreate('set-bonuses'));
  };
  $('#setSearch').oninput=paint; $('#setRarity').oninput=paint; paint();
}

async function fetchTable(full, limit=200, offset=0) {
  const key=`${full}:${limit}:${offset}`;
  if (app.tableCache.has(key)) return app.tableCache.get(key);
  const [schema,table]=full.split('.');
  const data=await api(`/api/table/${schema}/${table}?limit=${limit}&offset=${offset}`);
  app.tableCache.set(key,data); return data;
}

function rawTableHtml(payload, maxCols=12) {
  const rows=payload.rows||[];
  if (!rows.length) return `<div class="empty">Bảng ${esc(payload.table)} đang không có dữ liệu trong ${esc(payload.mode)}.</div>`;
  const cols=[...new Set(rows.flatMap(r=>Object.keys(r)))].slice(0,maxCols);
  return `<div class="table-wrap"><table><thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${cols.map(c=>`<td title="${esc(fmt(r[c]))}">${esc(trunc(r[c],60))}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="pagination"><span>${esc(payload.table)} • ${rows.length}/${fmt(payload.total)} rows hiển thị</span></div>`;
}

async function renderTableHub(title, eyebrow, allowed) {
  await ensureCore(); setPageMeta(title,eyebrow); hideNotice();
  const available=allowed.filter(full=>{
    const [s,t]=full.split('.'); return (app.schemas[s]||[]).some(x=>x.table===t);
  });
  pageEl.innerHTML=`<div class="split"><div class="card table-list" id="hubList">${available.map((x,i)=>`<button data-table="${x}" class="${i===0?'active':''}"><span>${esc(x)}</span><span>›</span></button>`).join('')}</div><div class="card" id="hubData"><div class="empty">Chọn bảng.</div></div></div>`;
  async function select(full, btn){
    $$('#hubList button').forEach(b=>b.classList.toggle('active',b===btn));
    $('#hubData').innerHTML='<div class="empty">Đang tải…</div>';
    try { $('#hubData').innerHTML=rawTableHtml(await fetchTable(full,300,0)); }
    catch(e){ $('#hubData').innerHTML=`<div class="empty">${esc(e.message)}</div>`; }
  }
  $$('#hubList button').forEach(btn=>btn.onclick=()=>select(btn.dataset.table,btn));
  const first=$('#hubList button'); if(first) select(first.dataset.table,first);
}

async function renderContent() { return renderTableHub('Content', 'ADMIN / GAME CONFIG', CONTENT_FAVORITES); }
async function renderLiveOps() { return renderTableHub('LiveOps', 'ADMIN / LIVEOPS', LIVEOPS_TABLES); }
async function renderOps() { return renderTableHub('Vận hành & Audit', 'ADMIN / OPERATIONS', OPS_TABLES); }

async function renderDiscordOps() { return renderTableHub('Discord Ops', 'ADMIN / DISCORD OPERATIONS', DISCORD_OPS_TABLES); }

async function renderDomainHub(key) {
  await ensureCore();
  const cfg=DOMAIN_CONFIG[key];
  const resources=await ensureCrudResources();
  setPageMeta(cfg.title,cfg.eyebrow); hideNotice();
  const resourceRows=cfg.resources.map(k=>resources.find(r=>r.key===k)).filter(Boolean);
  const runtime=cfg.runtime.filter(full=>{const [sc,t]=full.split('.');return (app.schemas[sc]||[]).some(x=>x.table===t);});
  pageEl.innerHTML=`
    <div class="domain-hero card card-pad"><div><div class="eyebrow">CONTROL CENTER</div><h2>${esc(cfg.title)}</h2><p class="muted">Definition/config dùng CRUD có kiểm soát. Runtime liên quan được mở cạnh bên để đối chiếu dữ liệu thật.</p></div><div class="domain-kpis"><div><b>${resourceRows.length}</b><span>CRUD resources</span></div><div><b>${runtime.length}</b><span>runtime tables</span></div></div></div>
    <div class="section-head"><div><div class="section-title">Definition / Config CRUD</div><div class="section-sub">Create • Read • Update • Delete • audit log</div></div></div>
    <div class="resource-card-grid">${resourceRows.map(r=>`<div class="card resource-card"><div><div class="resource-card-title">${esc(r.label)}</div><div class="code">${esc(r.table)}</div></div><div class="resource-card-actions"><button class="btn btn-secondary btn-small" data-domain-open="${esc(r.key)}">Mở CRUD</button><button class="btn btn-primary btn-small" data-domain-create="${esc(r.key)}" ${app.meta.mode==='live'&&app.meta.write_enabled?'':'disabled'}>＋ Tạo</button></div></div>`).join('')||'<div class="card empty">Không có resource.</div>'}</div>
    <div class="section-head"><div><div class="section-title">Runtime / State liên quan</div><div class="section-sub">Read-only để không bypass gameplay validation</div></div></div>
    <div class="resource-card-grid runtime-cards">${runtime.map(t=>`<div class="card resource-card"><div><div class="resource-card-title">${esc(t.split('.')[1])}</div><div class="code">${esc(t)}</div></div><button class="btn btn-secondary btn-small" data-runtime-open="${esc(t)}">Xem dữ liệu</button></div>`).join('')}</div>`;
  $$('[data-domain-open]').forEach(b=>b.onclick=()=>{app.pendingCrudResource=b.dataset.domainOpen;location.hash='#crud';});
  $$('[data-domain-create]').forEach(b=>b.onclick=()=>openCrudCreate(b.dataset.domainCreate));
  $$('[data-runtime-open]').forEach(b=>b.onclick=()=>openRawTable(b.dataset.runtimeOpen));
}

async function renderMedia() {
  await ensureCore();
  if(!app.items)app.items=await api('/api/items');
  setPageMeta('Kho ảnh / Media','ADMIN / DIRECT FILE UPLOAD + HEALTH');
  const [stats,assets,health]=await Promise.all([api('/api/media/stats'),api('/api/media/assets?limit=1000'),api('/api/media/health')]);
  const missing=app.items.filter(i=>!i.image_url && !String(i.item_code||'').toUpperCase().includes('SAMPLE'));
  const withImg=app.items.filter(i=>i.image_url && !String(i.item_code||'').toUpperCase().includes('SAMPLE'));
  if(stats.backend==='filesystem' && app.meta.mode==='live') showNotice('Media đang dùng filesystem fallback. Khuyến nghị chạy sql/30_shared_media_assets.sql để bot/web cùng đọc binary từ PostgreSQL.', 'warning'); else hideNotice();
  pageEl.innerHTML=`
    <div class="grid grid-4">
      ${metric('Ảnh production',withImg.length,'item có PRIMARY artwork')}
      ${metric('Còn thiếu ảnh',missing.length,'production item')}
      ${metric('Media assets',stats.files,stats.backend)}
      ${metric('Orphan assets',health.orphan_count,`${health.duplicate_group_count} nhóm duplicate SHA`)}
    </div>
    <div class="media-hero card card-pad"><div><h3>Direct Upload — không nhập link</h3><p class="muted">File từ Windows → validate/convert WebP → shared media DB → item image_asset_key. v4 hỗ trợ thêm Media Gallery nhiều ảnh/item; PRIMARY vẫn là ảnh Discord bot dùng mặc định.</p></div><div class="drawer-actions"><button id="mediaBulkBtn" class="btn btn-primary">▣ Upload nhiều ảnh</button><button id="mediaZipBtn" class="btn btn-secondary">ZIP Bulk</button></div></div>
    <div class="section-head"><div><div class="section-title">Thiếu artwork (${missing.length})</div><div class="section-sub">Bấm Item để upload trực tiếp</div></div></div>
    <div class="missing-image-grid">${missing.slice(0,120).map(i=>`<button class="missing-image-card" data-missing-item="${esc(i.item_def_id)}"><span class="item-icon r-${esc(i.rarity||'COMMON')}">${esc((i.equipment_slot||'IT').slice(0,2))}</span><span><b>${esc(i.item_name||i.item_code)}</b><small>${esc(i.item_code)}</small></span></button>`).join('')||'<div class="card empty">Tất cả production item đã có ảnh.</div>'}</div>
    <div class="section-head"><div><div class="section-title">Media health</div><div class="section-sub">Asset không còn reference có thể cleanup an toàn</div></div></div>
    <div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Orphan asset</th><th>Size</th><th>Updated</th><th></th></tr></thead><tbody>${(health.orphans||[]).slice(0,100).map(a=>`<tr><td class="code">${esc(a.asset_key)}</td><td>${fmt(Math.round(Number(a.size_bytes||0)/1024))} KB</td><td>${esc(fmt(a.updated_at))}</td><td><button class="btn btn-danger btn-small" data-orphan-delete="${esc(a.asset_key)}" ${app.meta.mode==='live'&&app.meta.write_enabled?'':'disabled'}>Xóa orphan</button></td></tr>`).join('')||'<tr><td colspan="4"><div class="empty compact-empty">Không có orphan asset.</div></td></tr>'}</tbody></table></div></div>
    <div class="section-head"><div><div class="section-title">Asset gần đây</div><div class="section-sub">${esc(stats.backend)} backend • ${Number(stats.used_bytes||0)/1024/1024 < 1024 ? (Number(stats.used_bytes||0)/1024/1024).toFixed(1)+' MB' : (Number(stats.used_bytes||0)/1024/1024/1024).toFixed(2)+' GB'}</div></div></div>
    <div class="media-gallery">${(assets.rows||[]).slice(0,100).map(a=>`<div class="card media-card"><div class="media-card-img"><img src="${esc(a.url)}?t=${Date.now()}" alt=""></div><div class="media-card-meta"><b>${esc(a.original_filename||a.asset_key.split('/').pop())}</b><div class="muted tiny">${fmt(a.width||'—')}×${fmt(a.height||'—')} • ${fmt(Math.round(Number(a.size_bytes||0)/1024))} KB</div></div></div>`).join('')||'<div class="card empty">Chưa có media asset.</div>'}</div>`;
  $('#mediaBulkBtn').onclick=openBulkImageUpload; $('#mediaZipBtn').onclick=()=>location.hash='#bulk';
  $$('[data-missing-item]').forEach(b=>b.onclick=()=>openItem(b.dataset.missingItem));
  $$('[data-orphan-delete]').forEach(b=>b.onclick=async()=>{if(!confirm(`Xóa orphan asset ${b.dataset.orphanDelete}?`))return;const h=writeHeaders(false);if(!h)return;try{await api(`/api/media/assets?asset_key=${encodeURIComponent(b.dataset.orphanDelete)}`,{method:'DELETE',headers:h});showNotice('Đã xóa orphan media asset và ghi audit.','warning');await renderMedia();}catch(e){alert(e.message);}});
}

async function ensureCrudResources() {
  if (!app.crudResources) app.crudResources=await api('/api/crud/resources');
  return app.crudResources;
}
async function getCrudSchema(resource) {
  if (!app.crudSchemaCache.has(resource)) app.crudSchemaCache.set(resource, await api(`/api/crud/${resource}/schema`));
  return app.crudSchemaCache.get(resource);
}
function pkForRow(schema,row) {
  const pk={};
  for(const k of schema.primary_key||[]) pk[k]=row[k];
  return pk;
}
function crudFieldInput(col,value,creating=false) {
  const name=col.column_name;
  const disabled = creating ? !col.writable_create : !col.writable_update;
  const nullable=col.is_nullable==='YES';
  const v=value===undefined||value===null?'':value;
  if(col.enum_values?.length){
    const names={TOWER:'Tháp',ABYSS:'Vực sâu',SECTION:'Vượt ải',HUNT:'Săn quái',FACTION_BOSS:'Boss phe',RAID:'Đột kích',WORLD_BOSS:'Boss thế giới',CLAN_BOSS:'Boss bang hội'};
    return `<select data-crud-field="${esc(name)}" ${disabled?'disabled':''}><option value="" ${v===''?'selected':''}>${nullable?'Để trống':'-- chọn --'}</option>${col.enum_values.map(x=>`<option value="${esc(x)}" ${String(v)===String(x)?'selected':''}>${esc(names[x]||x)}</option>`).join('')}</select>`;
  }
  if(col.data_type==='boolean'){
    return `<select data-crud-field="${esc(name)}" ${disabled?'disabled':''}><option value="" ${v===''?'selected':''}>${nullable?'Để trống':'Chọn'}</option><option value="true" ${v===true?'selected':''}>Có</option><option value="false" ${v===false?'selected':''}>Không</option></select>`;
  }
  if(['json','jsonb'].includes(col.data_type) || col.data_type==='ARRAY'){
    const txt = v===''?'':JSON.stringify(v,null,2);
    return `<textarea data-crud-field="${esc(name)}" data-kind="${col.data_type}" ${disabled?'disabled':''}>${esc(txt)}</textarea>`;
  }
  const type = ['smallint','integer','bigint','numeric','decimal','real','double precision'].includes(col.data_type) ? 'number' : 'text';
  const step = ['numeric','decimal','real','double precision'].includes(col.data_type) ? 'any' : '1';
  return `<input data-crud-field="${esc(name)}" type="${type}" step="${step}" value="${esc(v)}" ${disabled?'disabled':''}>`;
}
function parseCrudValue(col,el) {
  const raw=el.value;
  if(raw==='' && col.is_nullable==='YES') return null;
  if(col.data_type==='boolean') return raw===''?null:raw==='true';
  if(['smallint','integer','bigint'].includes(col.data_type)){if(raw==='')return null;const n=StructuredEditor.parseNumber(raw);if(!Number.isInteger(n))throw Error('Cần nhập số nguyên');return n;}
  if(['numeric','decimal','real','double precision'].includes(col.data_type)) return raw===''?null:StructuredEditor.parseNumber(raw);
  if(['json','jsonb'].includes(col.data_type)) {
    if(raw.trim()==='') return col.is_nullable==='YES'?null:{};
    return JSON.parse(raw);
  }
  if(col.data_type==='ARRAY') {
    if(raw.trim()==='') return col.is_nullable==='YES'?null:[];
    if(raw.trim().startsWith('[')) return JSON.parse(raw);
    return raw.split(',').map(x=>x.trim()).filter(Boolean);
  }
  return raw==='' && col.is_nullable==='YES' ? null : raw;
}
async function openCrudCreate(resource){ return openCrudEditor(resource,null); }
async function openCrudEditor(resource,row) {
  const schema=await getCrudSchema(resource);
  if(schema.mode!=='live') { alert('CRUD chỉ hoạt động khi Admin đang kết nối PostgreSQL LIVE. Snapshot chỉ để xem.'); return; }
  const resources=await ensureCrudResources();
  const r=resources.find(x=>x.key===resource);
  const creating=!row;
  const fields=schema.columns.filter(c=>!c.protected && (creating?c.writable_create:true) && (creating||advancedModeEnabled()||!technicalColumn(c)));
  openDrawer(creating?`Tạo ${r?.label||resource}`:(row.display_name_vi||row.code||row.set_code||row.event_code||row.id||r?.label||resource), creating?'TẠO CẤU HÌNH':'SỬA CẤU HÌNH', `
    <div class="crud-head-note"><span>Nhập trực tiếp từng trường rồi lưu. Mọi thay đổi đều có lịch sử.</span><b class="advanced-only">${esc(schema.table)}</b></div>
    ${resource==='enemy-bases'?'<p class="muted">Chỉ số áp dụng cho trận mới. Bật “Dùng base này trong trận mới” sau khi kiểm tra đầy đủ.</p>':''}
    <div class="form-grid crud-form" id="crudForm">
      ${fields.map(c=>`<div class="field ${['json','jsonb','ARRAY'].includes(c.data_type)?'full':''}"><label>${esc(friendlyField(c.column_name))} ${c.primary_key?'<span class="pk-tag advanced-only">Khóa chính</span>':''}<span class="field-type advanced-only">${esc(c.formatted_type||c.data_type)}</span></label>${crudFieldInput(c,row?.[c.column_name],creating)}${c.column_default?`<div class="field-hint advanced-only">Mặc định: ${esc(trunc(c.column_default,80))}</div>`:''}</div>`).join('')}
    </div>
    <div class="drawer-actions"><button id="crudSave" class="btn btn-primary">${creating?'Tạo mới':'Lưu thay đổi'}</button>${!creating?'<button id="crudDelete" class="btn btn-danger">Xóa cấu hình</button>':''}</div>
  `);
  $('#crudSave').onclick=async()=>{
    if(!Array.from($('#crudForm').querySelectorAll('input,select')).every(el=>el.reportValidity()))return;
    const payload={};
    try{
      for(const c of schema.columns){
        const el=$(`[data-crud-field="${CSS.escape(c.column_name)}"]`);
        if(!el||el.disabled)continue;
        const val=parseCrudValue(c,el);
        if(creating){
          if((val===null||val==='') && c.column_default) continue;
          if((val===null||val==='') && c.is_nullable==='YES') continue;
          payload[c.column_name]=val;
        }else{
          const old=row[c.column_name];
          if(JSON.stringify(old)!==JSON.stringify(val)) payload[c.column_name]=val;
        }
      }
    }catch(e){alert(`Dữ liệu form không hợp lệ: ${e.message}`);return;}
    if(!Object.keys(payload).length){alert('Không có thay đổi để lưu.');return;}
    const headers=writeHeaders(true); if(!headers)return;
    try{
      if(creating) await api(`/api/crud/${resource}`,{method:'POST',headers,body:JSON.stringify(payload)});
      else {
        if(resource==='enemy-bases')payload._expected_version=row.version;
        const pk=encodeURIComponent(JSON.stringify(pkForRow(schema,row)));
        await api(`/api/crud/${resource}?pk=${pk}`,{method:'PATCH',headers,body:JSON.stringify(payload)});
      }
      if(resource==='item-defs'){app.items=null;app.dashboard=null;}
      if(resource==='equipment-sets'||resource==='set-bonuses')app.sets=null;
      app.tableCache.clear(); closeDrawer(); showNotice(`${creating?'Đã tạo':'Đã cập nhật'} ${r?.label||resource} LIVE.`,'warning'); await renderCrudStudio(resource);
    }catch(e){alert(e.message);}
  };
  if(!creating) $('#crudDelete').onclick=async()=>{
    if(!schema.primary_key?.length){alert('Bảng này không có primary key nên Admin không cho xóa generic.');return;}
    if(!confirm(`Xóa record khỏi ${schema.table}? PostgreSQL sẽ chặn nếu record đang được gameplay tham chiếu.`))return;
    const headers=writeHeaders(false); if(!headers)return;
    const pk=encodeURIComponent(JSON.stringify(pkForRow(schema,row)));
    try{
      await api(`/api/crud/${resource}?pk=${pk}`,{method:'DELETE',headers});
      if(resource==='item-defs'){app.items=null;app.dashboard=null;}
      if(resource==='equipment-sets'||resource==='set-bonuses')app.sets=null;
      app.tableCache.clear();closeDrawer();showNotice(`Đã xóa record khỏi ${schema.table}.`,'warning');await renderCrudStudio(resource);
    }catch(e){alert(e.message);}
  };
}
async function renderCrudStudio(initialResource=null) {
  await ensureCore();
  const resources=await ensureCrudResources();
  setPageMeta('Quái, Boss & Cấu hình','CHỈNH SỬA TRỰC TIẾP');
  if(app.meta.mode==='snapshot') showNotice('CRUD Studio đang ở snapshot: xem được dữ liệu nhưng Create/Update/Delete bị khóa. Muốn bot nhận thay đổi phải kết nối PostgreSQL LIVE.','warning');
  else if(!app.meta.write_enabled) showNotice('Đã nối PostgreSQL LIVE nhưng write đang OFF. Bật ADMIN_WRITE_ENABLED=true để CRUD.','warning');
  else showNotice('CRUD chỉ mở cho các bảng definition/config được whitelist. Gameplay runtime state vẫn read-only để tránh sửa trực tiếp state nhạy cảm.','');
  const groups={};resources.forEach(r=>(groups[r.group]??=[]).push(r));
  pageEl.innerHTML=`<div class="split crud-split"><div class="card table-list" id="crudResourceList">${Object.entries(groups).map(([g,rs])=>`<div class="resource-group"><div class="resource-group-title">${esc(g)}</div>${rs.map(r=>`<button data-resource="${esc(r.key)}"><span>${esc(r.label)}</span><span class="muted">${r.row_count??''}</span></button>`).join('')}</div>`).join('')}</div><div id="crudData"><div class="card empty">Chọn một resource.</div></div></div>`;
  async function select(resource,btn){
    $$('#crudResourceList button').forEach(b=>b.classList.toggle('active',b===btn));
    $('#crudData').innerHTML='<div class="card empty">Đang tải…</div>';
    try{
      const [schema,data]=await Promise.all([getCrudSchema(resource),api(`/api/crud/${resource}?limit=1000`)]);
      const r=resources.find(x=>x.key===resource);
      const rows=data.rows||[]; const cols=(schema.columns?.filter(c=>!c.protected&&(advancedModeEnabled()||!technicalColumn(c))).map(c=>c.column_name)||[...new Set(rows.flatMap(x=>Object.keys(x)))]).filter(c=>!(resource==='item-defs'&&c==='image_asset_key'));
      const displayCols=resource==='enemy-bases'?['family','enemy_code','display_name_vi','hp','martial_power','mystic_power','enabled']:cols.slice(0,10);
      $('#crudData').innerHTML=`
        ${resource==='enemy-bases'?'<div class="card card-pad">Base áp dụng cho trận mới; trận đang đánh giữ chỉ số ban đầu. Mã Tháp/Vực sâu là Tầng:Phòng (ví dụ 12:1). Các mẫu khác đang tắt: bật sau khi chỉnh chỉ số. HP boss tại đây dùng cho trận cá nhân; tổng HP sự kiện chỉnh trong cấu hình boss.</div>':''}
        <div class="toolbar"><div class="search"><input id="crudSearch" placeholder="Tìm trong ${esc(r?.label||resource)}…"></div><span class="muted tiny">${fmt(data.total)} bản ghi<span class="advanced-only"> • ${esc(schema.table)}</span></span><button id="crudCreateBtn" class="btn btn-primary" ${app.meta.mode==='live'&&app.meta.write_enabled?'':'disabled'}>＋ Tạo mới</button></div>
        <div class="card table-card"><div class="table-wrap"><table><thead><tr>${displayCols.map(c=>`<th>${esc(friendlyField(c))}</th>`).join('')}<th></th></tr></thead><tbody id="crudRows"></tbody></table></div></div>`;
      const paint=()=>{
        const q=$('#crudSearch').value.trim().toLowerCase();const filtered=rows.filter(x=>!q||JSON.stringify(x).toLowerCase().includes(q));
        $('#crudRows').innerHTML=filtered.map((row,i)=>`<tr data-crud-idx="${i}" class="${schema.mode==='live'?'clickable':''}">${displayCols.map(c=>`<td title="${esc(fmt(row[c]))}">${esc(trunc(row[c],55))}</td>`).join('')}<td><button class="btn btn-secondary btn-small" data-edit-idx="${i}" ${schema.mode==='live'?'':'disabled'}>Sửa</button></td></tr>`).join('')||`<tr><td colspan="${displayCols.length+1}"><div class="empty">Chưa có dữ liệu.</div></td></tr>`;
        $$('[data-edit-idx]').forEach(b=>b.onclick=(ev)=>{ev.stopPropagation();openCrudEditor(resource,filtered[Number(b.dataset.editIdx)]);});
      };
      $('#crudSearch').oninput=paint;$('#crudCreateBtn').onclick=()=>openCrudCreate(resource);paint();
    }catch(e){$('#crudData').innerHTML=`<div class="card empty">${esc(e.message)}</div>`;}
  }
  $$('#crudResourceList button').forEach(b=>b.onclick=()=>select(b.dataset.resource,b));
  const preferred=initialResource?$$('#crudResourceList button').find(b=>b.dataset.resource===initialResource):null;
  const first=preferred||$('#crudResourceList button');if(first)select(first.dataset.resource,first);
}

async function renderRuntimeState() {
  await ensureCore();
  if(!app.runtimeGroups)app.runtimeGroups=await api('/api/runtime-groups');
  setPageMeta('Gameplay State','ADMIN / READ-ONLY RUNTIME');
  showNotice('Runtime state được mở rộng để quan sát Hero, Commander, Kingdom, March, Clan, Market, Economy và Combat. Trang này cố ý read-only; mutation runtime cần workflow riêng có validation/idempotency.','');
  const groups=Object.entries(app.runtimeGroups);
  pageEl.innerHTML=`<div class="split"><div class="card table-list" id="runtimeList">${groups.map(([g,ts])=>`<div class="resource-group"><div class="resource-group-title">${esc(g)}</div>${ts.map(t=>`<button data-table="${esc(t)}"><span>${esc(t.split('.')[1])}</span><span>›</span></button>`).join('')}</div>`).join('')}</div><div class="card" id="runtimeData"><div class="empty">Chọn bảng runtime.</div></div></div>`;
  async function select(full,btn){$$('#runtimeList button').forEach(b=>b.classList.toggle('active',b===btn));$('#runtimeData').innerHTML='<div class="empty">Đang tải…</div>';try{$('#runtimeData').innerHTML=rawTableHtml(await fetchTable(full,300,0));}catch(e){$('#runtimeData').innerHTML=`<div class="empty">${esc(e.message)}</div>`;}}
  $$('#runtimeList button').forEach(b=>b.onclick=()=>select(b.dataset.table,b));const first=$('#runtimeList button');if(first)select(first.dataset.table,first);
}

async function renderDatabase() {
  await ensureCore(); setPageMeta('Database Explorer','ADMIN / DATABASE'); hideNotice();
  const all=[];
  for (const [schema,tables] of Object.entries(app.schemas)) for (const t of tables) all.push(`${schema}.${t.table}`);
  pageEl.innerHTML=`<div class="toolbar"><div class="search"><input id="dbSearch" placeholder="Tìm schema.table…"></div><span class="muted tiny">${all.length} table trong whitelist của dump</span></div><div id="schemaGrid" class="schema-grid"></div>`;
  const paint=()=>{
    const q=$('#dbSearch').value.toLowerCase();
    const html=Object.entries(app.schemas).map(([schema,tables])=>{
      const filtered=tables.filter(t=>`${schema}.${t.table}`.toLowerCase().includes(q)); if(!filtered.length)return '';
      return `<div class="card schema-card"><div class="schema-name">${esc(schema)} <span class="muted">(${filtered.length})</span></div>${filtered.map(t=>`<div class="schema-table" data-table="${esc(schema+'.'+t.table)}"><span>${esc(t.table)}</span><span>${t.row_count == null?'?':fmt(t.row_count)}</span></div>`).join('')}</div>`;
    }).join('');
    $('#schemaGrid').innerHTML=html||'<div class="card empty">Không tìm thấy.</div>';
    $$('.schema-table').forEach(x=>x.onclick=()=>openRawTable(x.dataset.table));
  };
  $('#dbSearch').oninput=paint; paint();
}
async function openRawTable(full) {
  openDrawer(full,'DATABASE TABLE','<div class="empty">Đang tải…</div>');
  try { $('#drawerBody').innerHTML=rawTableHtml(await fetchTable(full,200,0),10); }
  catch(e){ $('#drawerBody').innerHTML=`<div class="empty">${esc(e.message)}</div>`; }
}

async function renderStaged() {
  await ensureCore(); setPageMeta('Staged changes','ADMIN / CHANGE REVIEW'); hideNotice();
  const changes=Object.values(getStaged()); const sql=allStagedSql();
  pageEl.innerHTML=`
    <div class="grid grid-2">
      <div class="card card-pad"><div class="section-title">${changes.length} thay đổi đang stage</div><div class="section-sub">Lưu trong browser localStorage, chưa đụng DB.</div></div>
      <div class="card card-pad"><div class="section-title">Safe-by-default export</div><div class="section-sub">SQL xuất ra mặc định ROLLBACK; bạn phải review rồi tự đổi sang COMMIT.</div></div>
    </div>
    <div class="section-head"><div><div class="section-title">Change list</div></div><div><button id="clearStage" class="btn btn-danger btn-small">Xóa tất cả stage</button></div></div>
    <div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Entity</th><th>Item</th><th>Fields</th><th>Staged at</th><th></th></tr></thead><tbody>
      ${changes.map(c=>`<tr><td class="code">${esc(c.entity)}</td><td><b>${esc(c.name||c.code)}</b><div class="code">${esc(c.code)}</div></td><td>${esc(Object.keys(c.patch||{}).join(', '))}</td><td>${esc(c.staged_at)}</td><td><button class="btn btn-danger btn-small" data-remove="${esc(c.id)}">Xóa</button></td></tr>`).join('')||'<tr><td colspan="5"><div class="empty">Chưa có staged changes.</div></td></tr>'}
    </tbody></table></div></div>
    <div class="section-head"><div><div class="section-title">SQL preview</div><div class="section-sub">Không tự chạy. Dùng để review/commit có chủ đích.</div></div><button id="downloadSql" class="btn btn-primary btn-small">Tải .sql</button></div>
    <pre class="sql-block">${esc(sql)}</pre>`;
  $$('[data-remove]').forEach(b=>b.onclick=()=>{const s=getStaged();delete s[b.dataset.remove];setStaged(s);renderStaged();});
  $('#clearStage').onclick=()=>{if(confirm('Xóa toàn bộ staged changes?')){setStaged({});renderStaged();}};
  $('#downloadSql').onclick=()=>downloadText('lost_kingsland_admin_staged_changes.sql',allStagedSql());
}

const CONTENT_MEDIA_RESOURCE={item:'item-defs',character:'characters',boss:'faction-bosses',enemy:'enemies',commander:'commander-defs',set:'equipment-sets',technique:'techniques',building:'buildings',research:'research',race:'races',path:'paths',affinity:'affinities',sect:'sects',region:'regions','clan-boss':'clan-boss-defs','clan-tech':'clan-tech-defs'};

async function renderContentMedia(){
  await ensureCore();
  setPageMeta('Content Media Studio','ADMIN / V27 SHARED MEDIA');
  if(app.meta.mode!=='live'){showNotice('Content Media Studio cần PostgreSQL LIVE. Snapshot không thể upload ảnh.','warning');pageEl.innerHTML='<div class="card empty">Hãy cấu hình DATABASE_URL tới lost_kingsland_v4_reconciled.</div>';return;}
  const kinds=await api('/api/content-media/kinds');
  hideNotice();
  pageEl.innerHTML=`
    <div class="domain-hero card card-pad"><div><div class="eyebrow">ONE MEDIA SOURCE</div><h2>Ảnh dùng chung cho Admin • Web • Discord Bot</h2><p class="muted">Upload file trực tiếp. Không nhập URL. Item/Character giữ image_asset_key; các content khác dùng platform.entity_media_links. Tất cả binary ở platform.media_assets.</p></div><div class="domain-kpis"><div><b>${kinds.length}</b><span>entity kinds</span></div><div><b>V27</b><span>database</span></div></div></div>
    <div class="toolbar" style="margin-top:14px">
      <select id="cmKind">${kinds.map(k=>`<option value="${esc(k.kind)}">${esc(k.kind.toUpperCase())} • ${esc(k.table)}</option>`).join('')}</select>
      <div class="search"><input id="cmSearch" placeholder="Tìm tên hoặc code…"></div>
      <button id="cmRefresh" class="btn btn-secondary">↻ Refresh</button>
    </div>
    <div id="cmMeta" class="muted tiny"></div>
    <div id="cmGrid" class="content-media-grid"><div class="card empty">Đang tải…</div></div>`;
  const paint=async()=>{
    const kind=$('#cmKind').value,q=$('#cmSearch').value.trim();
    $('#cmGrid').innerHTML='<div class="card empty">Đang tải…</div>';
    try{
      const r=await api(`/api/content-media/${encodeURIComponent(kind)}?q=${encodeURIComponent(q)}&limit=1000`);
      $('#cmMeta').textContent=`${r.total} ${kind} • Primary artwork dùng chung cho Web/Bot`;
      $('#cmGrid').innerHTML=r.rows.map(x=>`<article class="card content-media-card">
        <div class="content-media-art">${x.image_url?`<img src="${esc(x.image_url)}?t=${Date.now()}" alt="">`:`<span>${esc((x.code||kind).slice(0,2))}</span>`}</div>
        <div class="content-media-info"><b title="${esc(x.display_name)}">${esc(x.display_name||x.code)}</b><small>${esc(x.code)}</small></div>
        <div class="content-media-actions">
          <button class="btn btn-primary btn-small" data-cm-upload="${esc(x.entity_id)}">${x.image_url?'Thay ảnh':'＋ Thêm ảnh'}</button>
          <button class="btn btn-secondary btn-small" data-cm-gallery="${esc(x.entity_id)}">Gallery</button>
          <button class="btn btn-secondary btn-small" data-cm-edit="${esc(x.entity_id)}">Sửa info</button>
        </div>
      </article>`).join('')||'<div class="card empty">Không có dữ liệu.</div>';
      $$('[data-cm-upload]').forEach(b=>b.onclick=()=>pickContentImage(kind,b.dataset.cmUpload,paint));
      $$('[data-cm-gallery]').forEach(b=>b.onclick=()=>openContentGallery(kind,b.dataset.cmGallery,paint));
      $$('[data-cm-edit]').forEach(b=>b.onclick=()=>{app.pendingCrudResource=CONTENT_MEDIA_RESOURCE[kind];location.hash='#crud';});
    }catch(e){$('#cmGrid').innerHTML=`<div class="card empty">${esc(e.message)}</div>`;}
  };
  $('#cmKind').onchange=paint; let timer; $('#cmSearch').oninput=()=>{clearTimeout(timer);timer=setTimeout(paint,180)};$('#cmRefresh').onclick=paint;await paint();
}

function pickContentImage(kind,entityId,after){
  if(!(app.meta.mode==='live'&&app.meta.write_enabled)){alert('Bật ADMIN_WRITE_ENABLED=true trước khi upload.');return;}
  const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp,image/gif';
  input.onchange=async()=>{const f=input.files?.[0];if(!f)return;const headers=writeHeaders(false);if(!headers)return;const fd=new FormData();fd.append('file',f);try{await api(`/api/content-media/${encodeURIComponent(kind)}/${encodeURIComponent(entityId)}/image?role=PRIMARY`,{method:'POST',headers,body:fd});showNotice(`Đã upload PRIMARY artwork cho ${kind}. Bot/Web có thể đọc ngay từ shared DB.`,'warning');await after();}catch(e){alert(e.message);}};input.click();
}

async function openContentGallery(kind,entityId,after){
  const g=await api(`/api/content-media/${encodeURIComponent(kind)}/${encodeURIComponent(entityId)}/gallery`);
  openDrawer(`${kind.toUpperCase()} media`,'SHARED MEDIA GALLERY',`
    <div class="media-contract">PRIMARY = ảnh mặc định Bot/Web. DETAIL/THUMBNAIL/GALLERY có thể dùng cho website. Binary lưu trong PostgreSQL.</div>
    <div class="gallery-grid" id="cmGalleryGrid">${g.rows.map(x=>`<div class="gallery-card ${x.is_primary?'primary':''}"><img src="${esc(x.url)}" alt=""><div><b>${esc(x.media_role)}</b><div class="code">${esc(x.asset_key)}</div><div class="muted tiny">${esc(x.width||'?')}×${esc(x.height||'?')}</div></div><div class="gallery-actions">${x.is_primary?'':'<button class="btn btn-primary btn-small" data-cmg-primary="'+esc(x.asset_key)+'">Đặt PRIMARY</button>'}<button class="btn btn-danger btn-small" data-cmg-delete="${esc(x.asset_key)}">Xóa</button></div></div>`).join('')||'<div class="empty compact-empty">Chưa có ảnh.</div>'}</div>
    <div class="gallery-upload-row"><select id="cmGalleryRole"><option>GALLERY</option><option>DETAIL</option><option>THUMBNAIL</option><option>DISCORD</option><option>PRIMARY</option></select><input id="cmGalleryFile" type="file" accept="image/*"><button id="cmGalleryUpload" class="btn btn-primary">Upload</button></div>`);
  $$('[data-cmg-primary]').forEach(b=>b.onclick=async()=>{const h=writeHeaders(true);if(!h)return;await api(`/api/content-media/${encodeURIComponent(kind)}/${encodeURIComponent(entityId)}/primary`,{method:'POST',headers:h,body:JSON.stringify({asset_key:b.dataset.cmgPrimary})});await openContentGallery(kind,entityId,after);await after();});
  $$('[data-cmg-delete]').forEach(b=>b.onclick=async()=>{if(!confirm('Xóa ảnh này khỏi entity?'))return;const h=writeHeaders(false);if(!h)return;await api(`/api/content-media/${encodeURIComponent(kind)}/${encodeURIComponent(entityId)}/image?asset_key=${encodeURIComponent(b.dataset.cmgDelete)}`,{method:'DELETE',headers:h});await openContentGallery(kind,entityId,after);await after();});
  $('#cmGalleryUpload').onclick=async()=>{const f=$('#cmGalleryFile').files?.[0];if(!f){alert('Chọn file ảnh.');return;}const h=writeHeaders(false);if(!h)return;const fd=new FormData();fd.append('file',f);const role=$('#cmGalleryRole').value;await api(`/api/content-media/${encodeURIComponent(kind)}/${encodeURIComponent(entityId)}/image?role=${encodeURIComponent(role)}`,{method:'POST',headers:h,body:fd});await openContentGallery(kind,entityId,after);await after();};
}


async function renderCharacters(){
  await ensureCore(); setPageMeta('Nhân vật & Ảnh','ADMIN / CHARACTER ARTWORK STUDIO'); hideNotice();
  let data;
  try{data=await api('/api/characters?limit=1000');}catch(e){pageEl.innerHTML=`<div class="card empty">${esc(e.message)}</div>`;return;}
  const rows=data.rows||[];
  const configNote=data.config_fallback
    ? `<div class="catalog-version-note"><b>Character catalog:</b> ${esc(data.content_config_version||'—')} <span>• gameplay config hiện tại ${esc(data.requested_gameplay_config||'—')} không chứa character_defs nên Admin tự dùng catalog gần nhất có dữ liệu.</span></div>`
    : `<div class="catalog-version-note ok"><b>Character catalog:</b> ${esc(data.content_config_version||data.requested_gameplay_config||'—')}</div>`;
  pageEl.innerHTML=`
    <div class="domain-hero card card-pad"><div><div class="eyebrow">40 CHARACTER CONTENT</div><h2>Character Artwork Studio</h2><p class="muted">Quản lý dữ liệu và upload ảnh trực tiếp cho các nhân vật. PRIMARY tự đồng bộ <code>hero.character_defs.image_asset_key</code>; Bot/Web đọc cùng shared media DB.</p></div><div class="domain-kpis"><div><b>${rows.length}</b><span>characters</span></div><div><b>${rows.filter(x=>x.image_url).length}</b><span>có ảnh</span></div></div></div>
    ${configNote}
    <div class="toolbar"><div class="search"><input id="charSearch" placeholder="Tìm tên, code, role, affinity…"></div><select id="charRarity"><option value="">Tất cả rarity</option>${RARITY_ORDER.map(r=>`<option>${r}</option>`).join('')}</select><select id="charImage"><option value="">Ảnh: tất cả</option><option value="missing">Chưa có ảnh</option><option value="has">Đã có ảnh</option></select><button id="charCrud" class="btn btn-secondary">✎ CRUD Character Data</button></div>
    <div id="characterGrid" class="character-grid"></div>`;
  const paint=()=>{const q=$('#charSearch').value.toLowerCase(),rar=$('#charRarity').value,img=$('#charImage').value;const list=rows.filter(x=>(!q||JSON.stringify(x).toLowerCase().includes(q))&&(!rar||x.rarity===rar)&&(!img||(img==='has'?!!x.image_url:!x.image_url)));$('#characterGrid').innerHTML=list.map(x=>`<article class="card character-card" data-character="${esc(x.code)}"><div class="character-art ${x.image_url?'has-art':''}">${x.image_url?`<img src="${esc(x.image_url)}?t=${Date.now()}" alt="">`:`<span>${esc((x.display_name_vi||x.code).slice(0,2))}</span>`}<div class="character-rarity">${rarityBadge(x.rarity)}</div></div><div class="character-info"><h3>${esc(x.display_name_vi)}</h3><div class="code">${esc(x.code)}</div><div class="char-tags"><span>${esc(x.combat_role)}</span><span>${esc(x.affinity_code)}</span></div><div class="muted tiny">${esc(trunc(x.signature_skill_vi,70))}</div></div><div class="character-actions"><button class="btn btn-primary btn-small" data-char-upload="${esc(x.code)}">${x.image_url?'Thay ảnh':'＋ Thêm ảnh'}</button><button class="btn btn-secondary btn-small" data-char-gallery="${esc(x.code)}">Gallery</button><button class="btn btn-secondary btn-small" data-char-detail="${esc(x.code)}">Chi tiết</button></div></article>`).join('')||'<div class="card empty">Không có nhân vật theo filter.</div>';
    $$('[data-char-upload]').forEach(b=>b.onclick=e=>{e.stopPropagation();pickContentImage('character',b.dataset.charUpload,async()=>{await renderCharacters();});});
    $$('[data-char-gallery]').forEach(b=>b.onclick=e=>{e.stopPropagation();openContentGallery('character',b.dataset.charGallery,async()=>{});});
    $$('[data-char-detail]').forEach(b=>b.onclick=e=>{e.stopPropagation();const x=rows.find(r=>r.code===b.dataset.charDetail);openCharacterDetail(x);});
  };
  $('#charSearch').oninput=paint;$('#charRarity').onchange=paint;$('#charImage').onchange=paint;$('#charCrud').onclick=()=>{app.pendingCrudResource='characters';location.hash='#crud';};paint();
}

function openCharacterDetail(x){
  openDrawer(x.display_name_vi||x.code,'CHARACTER / CONTENT DETAIL',`<div class="character-detail-hero">${x.image_url?`<img src="${esc(x.image_url)}?t=${Date.now()}">`:'<div class="image-empty image-empty-large">Chưa có ảnh</div>'}<div><div>${rarityBadge(x.rarity)}</div><h2>${esc(x.display_name_vi)}</h2><div class="code">${esc(x.code)}</div><p>${esc(x.lore_summary_vi||'')}</p></div></div><div class="grid grid-2">${detail('Combat role',x.combat_role)}${detail('Affinity',x.affinity_code)}${detail('Weapon theme',x.weapon_theme)}${detail('Power multiplier',x.rarity_power_mult)}</div><div class="card card-pad"><b>Signature Skill</b><p>${esc(x.signature_skill_vi||'—')}</p></div><div class="card card-pad"><b>Stat profile</b><pre class="json-block">${esc(JSON.stringify(x.stat_profile||{},null,2))}</pre></div><div class="drawer-actions"><button id="charDetailUpload" class="btn btn-primary">${x.image_url?'Thay PRIMARY':'＋ Upload PRIMARY'}</button><button id="charDetailGallery" class="btn btn-secondary">Media Gallery</button></div>`);
  $('#charDetailUpload').onclick=()=>pickContentImage('character',x.code,async()=>{await renderCharacters();});
  $('#charDetailGallery').onclick=()=>openContentGallery('character',x.code,async()=>{});
}

async function renderTestMedia(){
  await ensureCore(); setPageMeta('Ảnh test & Bot','ADMIN / ONE-CLICK MEDIA PIPELINE'); hideNotice();
  let plan;
  try{ plan=await api('/api/test-media/plan'); }
  catch(e){ pageEl.innerHTML=`<div class="card card-pad"><h3>Không tải được Test Media</h3><p class="muted">${esc(e.message)}</p></div>`; return; }
  const p=plan.permissions||{}, db=plan.db||{};
  const typeOptions=Object.entries(plan.by_type||{}).map(([k,v])=>`<option value="${esc(k)}">${esc(k)} (${esc(v)})</option>`).join('');
  pageEl.innerHTML=`
    <div class="media-seed-hero card card-pad">
      <div><div class="eyebrow">PLAYTEST MEDIA</div><h2>One-click Test Media</h2><p>Admin tự tải placeholder từ mapping có sẵn → lưu binary vào PostgreSQL → gắn PRIMARY → Bot/Web đọc cùng ảnh. Không phải copy file sang gameplay.</p></div>
      <div class="seed-health ${p.ready?'ready':'bad'}"><b>${p.ready?'READY':'NEEDS SQL'}</b><span>${esc(p.db_user||'DB permission')}</span></div>
    </div>
    <div class="grid grid-4 seed-metrics">
      ${metric('Mapping',plan.total,'entity có ảnh test')}
      ${metric('Item diversity',`${db.item_unique_assets||0}/${db.item_primary_links||0}`,'unique / primary')}
      ${metric('Set diversity',`${db.set_unique_assets||0}/${db.set_primary_links||0}`,'unique / primary')}
      ${metric('Test assets',db.test_assets||0,'TEST_PLACEHOLDER trong DB')}
    </div>
    ${db.diversity_ready?'':`<div class="inline-warning seed-warning"><b>Ảnh đa dạng CHƯA được áp dụng.</b> Nếu thấy kiểu <code>ITEM 480 links / 9 unique</code> hoặc <code>SET 20 / 1</code>, đó là placeholder cũ. Bấm <b>♻ Nâng placeholder cũ → Diverse 664</b>; ảnh thật do bạn upload sẽ được giữ nguyên.</div>`}
    ${p.ready?'':`<div class="inline-warning seed-warning"><b>Thiếu quyền DB.</b> Trong DBeaver chạy <code>sql/70_v62_test_media_permissions_hotfix.sql</code> trên <b>lost_kingsland_v4_reconciled</b>, restart Admin rồi quay lại đây.</div>`}
    <div class="seed-layout">
      <div class="card card-pad seed-action-card">
        <div class="step-no">1</div><h3>Chọn phạm vi</h3><p class="muted">Để trống loại = tất cả ${esc(plan.total)} entity.</p>
        <div class="field"><label>Loại content</label><select id="seedType"><option value="">Tất cả content</option>${typeOptions}</select></div>
        <div class="seed-presets">
          <button id="seedRebuildDiverse" class="btn btn-primary" ${p.ready?'':'disabled'}>♻ Nâng placeholder cũ → Diverse 664</button>
          <button id="seedDiverse30" class="btn btn-secondary" ${p.ready?'':'disabled'}>✨ Test 30 ảnh đa dạng</button>
          <button id="seedDiverseAll" class="btn btn-secondary" ${p.ready?'':'disabled'}>✨ Gắn ảnh đa dạng còn thiếu</button>
          <button id="seed20" class="btn btn-secondary" ${p.ready?'':'disabled'}>Test 20 ảnh nhanh (legacy)</button>
          <button id="seedMissing" class="btn btn-secondary" ${p.ready?'':'disabled'}>Gắn ảnh còn thiếu (mapping cũ)</button>
        </div>
        <div class="inline-warning"><b>V6.3 Diversity:</b> lần đầu sẽ tải kho Game-icons ~30 MB, sau đó tự chọn <b>silhouette khác nhau</b> theo slot + tên item + pet/boss/element + rarity và cache lại trên máy.</div><div class="muted tiny">Mặc định không đè artwork bạn đã upload thật.</div>
      </div>
      <div class="card card-pad seed-action-card">
        <div class="step-no">2</div><h3>Theo dõi tiến trình</h3><div id="seedJobState" class="seed-job-state">Đang kiểm tra…</div><pre id="seedLog" class="seed-log">Chưa chạy job.</pre>
      </div>
      <div class="card card-pad seed-action-card">
        <div class="step-no">3</div><h3>Check Bot / Web</h3><p class="muted">Kiểm tra shared DB + endpoint Item/Character tại Admin đang chạy.</p>
        <button id="seedCheck" class="btn btn-secondary">▶ Chạy kiểm tra Bot/Web</button>
        <pre id="seedCheckOut" class="seed-log small">Chưa kiểm tra.</pre>
      </div>
    </div>
    <details class="card card-pad seed-danger-zone"><summary>Công cụ test nâng cao</summary><div class="seed-danger-actions"><button id="seedReplace" class="btn btn-danger" ${p.ready?'':'disabled'}>Thay toàn bộ bằng ảnh test</button><button id="seedCleanup" class="btn btn-danger" ${p.ready?'':'disabled'}>Xóa toàn bộ ảnh TEST_PLACEHOLDER</button></div><p class="muted tiny">Chỉ dùng cho playtest. “Thay toàn bộ” sẽ đè PRIMARY artwork hiện có; “Xóa” chỉ xóa asset category TEST_PLACEHOLDER.</p></details>`;

  let pollTimer=null;
  async function pollJob(){
    try{
      const j=await api('/api/test-media/job');
      const state=$('#seedJobState'), log=$('#seedLog');
      if(state) state.innerHTML=`<span class="job-dot ${esc(j.status)}"></span><b>${esc((j.status||'idle').toUpperCase())}</b>${j.kind?`<span>${esc(j.kind)}</span>`:''}${j.returncode!==null&&j.returncode!==undefined?`<span>code ${esc(j.returncode)}</span>`:''}`;
      if(log){ log.textContent=(j.log||[]).join('\n')||'Chưa chạy job.'; log.scrollTop=log.scrollHeight; }
      if(j.status==='running'){ pollTimer=setTimeout(pollJob,900); }
      else if(j.status==='done'){ app.dashboard=null;app.commandCenter=null; setTimeout(async()=>{try{const fresh=await api('/api/test-media/plan'); showNotice(`Ảnh test hoàn tất: ${fresh.db?.primary_links||0} primary links • ${fresh.db?.test_assets||0} assets trong DB.`,'');}catch{}},250); }
    }catch(e){ if($('#seedJobState')) $('#seedJobState').textContent=e.message; }
  }
  async function startSeed(mode,limit=0,strategy='mapped'){
    const h=writeHeaders(true); if(!h)return;
    const entity_type=$('#seedType')?.value||'';
    try{ await api('/api/test-media/start',{method:'POST',headers:h,body:JSON.stringify({mode,limit,entity_type,strategy})}); showNotice(strategy==='diverse'?'Đã bắt đầu V6.3 Diverse Media. Lần đầu tải kho icon ~30 MB rồi tự match theo tên.':'Đã bắt đầu job ảnh test.','warning'); clearTimeout(pollTimer); pollJob(); }
    catch(e){ alert(e.message); }
  }
  $('#seedRebuildDiverse').onclick=async()=>{
    if(!confirm('Xóa CHỈ placeholder test cũ và dựng lại bộ 664 ảnh đa dạng? Artwork thật do bạn upload sẽ được giữ nguyên.')) return;
    const h=writeHeaders(true); if(!h)return;
    try{ await api('/api/test-media/rebuild-diverse',{method:'POST',headers:h,body:'{}'}); showNotice('Đang dọn placeholder cũ và dựng lại Diverse 664. Lần đầu có thể tải ~30 MB icon archive.','warning'); clearTimeout(pollTimer); pollJob(); }
    catch(e){ alert(e.message); }
  };
  $('#seedDiverse30').onclick=()=>startSeed('missing',30,'diverse');
  $('#seedDiverseAll').onclick=()=>startSeed('missing',0,'diverse');
  $('#seed20').onclick=()=>startSeed('missing',20,'mapped');
  $('#seedMissing').onclick=()=>startSeed('missing',0,'mapped');
  $('#seedReplace').onclick=()=>{ if(confirm('Thay PRIMARY của phạm vi đã chọn bằng ảnh test? Artwork thật có thể bị đè.')) startSeed('replace',0,'diverse'); };
  $('#seedCheck').onclick=async()=>{ const h=writeHeaders(true)||{'Content-Type':'application/json'}; const b=$('#seedCheck'); b.disabled=true;b.textContent='Đang check…';try{const r=await api('/api/test-media/check',{method:'POST',headers:h,body:'{}'});$('#seedCheckOut').textContent=r.output||JSON.stringify(r,null,2);showNotice(r.ok?'Bot/Web media check PASS.':'Check hoàn tất nhưng có lỗi; xem log bên dưới.',r.ok?'':'warning');}catch(e){$('#seedCheckOut').textContent=e.message;showNotice(e.message,'error');}finally{b.disabled=false;b.textContent='▶ Chạy kiểm tra Bot/Web';}};
  $('#seedCleanup').onclick=async()=>{if(!confirm('Xóa toàn bộ TEST_PLACEHOLDER khỏi shared media DB? Artwork thật không bị xóa.'))return;const h=writeHeaders(false);if(!h)return;try{const r=await api('/api/test-media/placeholders',{method:'DELETE',headers:h});showNotice(`Đã xóa ${r.deleted_assets} test assets và ${r.deleted_links} links.`,'warning');await renderTestMedia();}catch(e){alert(e.message);}};
  pollJob();
}

async function renderGiftcodes(){
  await ensureCore(); setPageMeta('Giftcode','ADMIN / LIVEOPS • REDEMPTION'); hideNotice();
  let stats,data,runtime;
  try{[stats,data,runtime]=await Promise.all([api('/api/giftcodes/stats'),api('/api/giftcodes?limit=1000'),api('/api/giftcodes/runtime')]);}
  catch(e){pageEl.innerHTML=`<div class="card card-pad"><h3>Giftcode chưa sẵn sàng</h3><p class="muted">${esc(e.message)}</p><div class="inline-warning">Runtime phải dùng Flyway V42+ trên đúng DB.</div></div>`;return;}
  const rows=data.rows||[];
  pageEl.innerHTML=`
    <div class="grid grid-4">${metric('Giftcodes',stats.total,'tổng campaign/code')}${metric('Active',stats.active,'đang có thể nhập')}${metric('Redemptions',stats.redemptions,'reservation/history')}${metric('Granted',stats.granted,`${stats.pending||0} pending grant`)}</div>
    <div class="domain-hero card card-pad"><div><div class="eyebrow">${runtime?.ready?'LIVE · DB + BOT CONNECTED':'BLOCKED · RUNTIME MISMATCH'}</div><h2>Giftcode Studio</h2><p class="muted">Admin web và <b>/giftcode</b> dùng trực tiếp cùng PostgreSQL authoritative. DB <b>${esc(runtime?.database_name||'—')}</b> · Flyway V${esc(runtime?.flyway||'—')} · ${esc(runtime?.gameplay_config||'—')}.</p></div><div class="drawer-actions"><button id="giftNew" class="btn btn-primary" ${runtime?.ready?'':'disabled'}>＋ Tạo Giftcode</button><button id="giftTest" class="btn btn-secondary">✓ Test code</button></div></div>
    <div class="toolbar"><div class="search"><input id="giftSearch" placeholder="Tìm code, tên, mô tả…"></div><select id="giftStatus"><option value="">Tất cả status</option><option>DRAFT</option><option>ACTIVE</option><option>PAUSED</option><option>EXPIRED</option><option>ARCHIVED</option></select></div>
    <div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Code</th><th>Tên</th><th>Status</th><th>Thời gian</th><th>Đã dùng</th><th>Per player</th><th>Reward</th><th></th></tr></thead><tbody id="giftRows"></tbody></table></div></div>`;
  const paint=()=>{const q=$('#giftSearch').value.toLowerCase(),st=$('#giftStatus').value;const list=rows.filter(x=>(!q||JSON.stringify(x).toLowerCase().includes(q))&&(!st||x.status===st));$('#giftRows').innerHTML=list.map(x=>`<tr><td><b class="code gift-code">${esc(x.code)}</b><div class="muted tiny">${esc(x.id)}</div></td><td>${esc(x.display_name)}<div class="muted tiny">${esc(trunc(x.description,64))}</div></td><td>${statusBadge(x.effective_status)}</td><td><div>${esc(fmt(x.starts_at))}</div><div class="muted tiny">→ ${esc(fmt(x.ends_at))}</div></td><td>${esc(fmt(x.redemption_count))} / ${esc(fmt(x.max_redemptions||'∞'))}</td><td>${esc(fmt(x.per_player_limit))}</td><td><code>${esc(trunc(x.reward_bundle,48))}</code></td><td><button class="btn btn-secondary btn-small" data-gift-edit="${esc(x.id)}">Mở</button></td></tr>`).join('')||'<tr><td colspan="8"><div class="empty">Chưa có giftcode.</div></td></tr>';$$('[data-gift-edit]').forEach(b=>b.onclick=()=>openGiftcode(rows.find(x=>String(x.id)===String(b.dataset.giftEdit))));};
  $('#giftSearch').oninput=paint;$('#giftStatus').onchange=paint;$('#giftNew').onclick=()=>openGiftcode(null);$('#giftTest').onclick=openGiftcodeTester;paint();
}

function giftcodeTitlePickerMarkup(count){
  return `<div class="field span-2 gift-title-picker"><label>Danh hiệu kèm giftcode (${count})</label><input id="gcTitleSearch" type="search" placeholder="Tìm tên, mã ID hoặc bậc…" autocomplete="off"><div id="gcTitleList" class="gift-title-list"></div><p id="gcTitleSummary" class="muted"></p><details class="gift-title-upload"><summary>Đổi ảnh danh hiệu đã chọn</summary><div class="gift-title-upload-body"><select id="gcArtworkTitle"></select><input id="gcArtworkFile" type="file" accept="image/png,image/jpeg,image/webp,image/gif"><img id="gcArtworkPreview" alt="Xem trước ảnh mới" hidden><button id="gcArtworkUpload" class="btn btn-secondary" type="button">Tải ảnh lên</button><p class="muted">Ảnh mới dùng cho mọi profile mang danh hiệu này; bot tự co vừa khung.</p></div></details></div>`;
}

async function openGiftcode(g){
  const creating=!g;
  const bundle=g?.reward_bundle||{assets:{GOLD:1000},items:[],titles:[]},assets=bundle.assets||{},preservedItems=bundle.items||[];
  const selectedTitles=new Set((bundle.titles||[]).map(x=>typeof x==='string'?x:x.title_code));
  let titleCatalog;
  try {const catalog=await api('/api/giftcodes/title-options');titleCatalog=(catalog.rows||[]).sort((a,b)=>(a.realm_ordinal||99)-(b.realm_ordinal||99)||a.display_name_vi.localeCompare(b.display_name_vi,'vi'));}
  catch(error){if(!/^404\b/.test(error.message)){showNotice(`Không tải được danh hiệu: ${error.message}`,'error');return;}try{const catalog=await api('/api/crud/title-defs?limit=1000');titleCatalog=(catalog.rows||[]).filter(x=>x.active&&x.source_type==='GIFTCODE');}catch(fallbackError){showNotice(`Không tải được danh hiệu: ${fallbackError.message}`,'error');return;}}
  const eligibility=g?.eligibility_json||{min_account_level:1,min_exploration_floor:1,account_status:'ACTIVE'};
  const rewardInput=(id,label,code)=>`<div class="field"><label>${label}</label><input id="${id}" type="number" min="0" value="${esc(assets[code]||'')}" placeholder="0"></div>`;
  openDrawer(creating?'Tạo Giftcode':g.code,creating?'GIFT CODE / CREATE':'GIFT CODE / EDIT',`<div class="grid grid-2"><div class="field span-2"><label>Code</label><div class="inline-fields"><input id="gcCode" value="${esc(g?.code||'')}"><button id="gcGenerate" class="btn btn-secondary btn-small">Random</button></div></div><div class="field span-2"><label>Mô tả</label><textarea id="gcDesc">${esc(g?.description||'')}</textarea></div><div class="field"><label>Trạng thái</label><select id="gcStatus">${['DRAFT','ACTIVE','PAUSED','EXPIRED','ARCHIVED'].map(x=>`<option ${g?.status===x?'selected':''}>${x}</option>`).join('')}</select></div><div class="field"><label>Giới hạn mỗi người</label><input id="gcPer" type="number" min="1" value="${esc(g?.per_player_limit||1)}"></div><div class="field"><label>Tổng lượt nhận (trống = không giới hạn)</label><input id="gcMax" type="number" min="1" value="${esc(g?.max_redemptions||'')}"></div><div class="field span-2"><label>Phần thưởng tài sản</label><div class="grid grid-4">${rewardInput('gcGold','Vàng','GOLD')}${rewardInput('gcGems','Gem','GEMS')}${rewardInput('gcJade','Ngọc','JADE')}${rewardInput('gcSp','Điểm kỹ năng','SKILL_POINT')}${rewardInput('gcWood','Gỗ','WOOD')}${rewardInput('gcFood','Lương thực','FOOD')}${rewardInput('gcOre','Quặng','ORE')}${rewardInput('gcEssence','Tinh hoa','ESSENCE')}${rewardInput('gcClan','Dấu ấn Clan','CLAN_MARKS')}${rewardInput('gcSeason','Xu mùa giải','SEASON_TOKEN')}</div></div><div class="field span-2"><div id="gcRewardPreview" class="inline-warning">Hãy kiểm tra đủ quà trước khi lưu. Giftcode chỉ trao đúng nội dung bên dưới.</div></div><div class="field span-2"><label>Reward Bundle JSON (nâng cao)</label><textarea id="gcReward">${esc(JSON.stringify(bundle,null,2))}</textarea></div><div class="field span-2"><label>Điều kiện nhận JSON</label><textarea id="gcEligibility">${esc(JSON.stringify(g?.eligibility_json||{min_account_level:1,min_exploration_floor:1,account_status:'ACTIVE'},null,2))}</textarea></div></div><div class="drawer-actions"><button id="gcSave" class="btn btn-primary">${creating?'Tạo Giftcode':'Lưu'}</button>${creating?'':`<button id="gcRedemptions" class="btn btn-secondary">Lịch sử nhập</button><button id="gcArchive" class="btn btn-danger">Archive</button>`}</div>`);
  $('#gcReward').closest('.field').remove();
  $('#gcRewardPreview').closest('.field').insertAdjacentHTML('beforebegin',giftcodeTitlePickerMarkup(titleCatalog.length));
  const eligibilityField=$('#gcEligibility').closest('.field');
  eligibilityField.innerHTML=`<label>Điều kiện nhận</label><div class="grid grid-2"><div class="field"><label>Account level tối thiểu</label><input id="gcMinLevel" type="number" min="1" step="1" value="${esc(eligibility.min_account_level||1)}"></div><div class="field"><label>Account level tối đa</label><input id="gcMaxLevel" type="number" min="1" step="1" value="${esc(eligibility.max_account_level||'')}"></div><div class="field"><label>Floor tối thiểu</label><input id="gcMinFloor" type="number" min="1" step="1" value="${esc(eligibility.min_exploration_floor||1)}"></div><div class="field"><label>Trạng thái tài khoản</label><select id="gcAccountStatus">${['ACTIVE','RESTRICTED','SUSPENDED'].map(x=>`<option ${String(eligibility.account_status||'ACTIVE')===x?'selected':''}>${x}</option>`).join('')}</select></div></div>`;
  $('#gcGenerate').onclick=async()=>{const h=writeHeaders(true);if(!h)return;const r=await api('/api/giftcodes/generate',{method:'POST',headers:h,body:JSON.stringify({prefix:'LK',length:10})});$('#gcCode').value=r.code;};
  const buildReward=()=>{const reward={assets:{},items:preservedItems,titles:[]};const nums=[['GOLD','#gcGold'],['GEMS','#gcGems'],['JADE','#gcJade'],['SKILL_POINT','#gcSp'],['WOOD','#gcWood'],['FOOD','#gcFood'],['ORE','#gcOre'],['ESSENCE','#gcEssence'],['CLAN_MARKS','#gcClan'],['SEASON_TOKEN','#gcSeason']];for(const [code,sel] of nums){const n=Number($(sel).value||0);if(n>0)reward.assets[code]=n;}selectedTitles.forEach(code=>reward.titles.push({title_code:code}));const count=Object.keys(reward.assets).length+reward.items.length+reward.titles.length;$('#gcRewardPreview').textContent=count?`Đã cấu hình ${Object.keys(reward.assets).length} loại tài sản và ${reward.titles.length} danh hiệu.`:'Chưa có phần thưởng. Giftcode sẽ không thể lưu.';return reward;};
  const paintTitlePicker=()=>{
    const query=$('#gcTitleSearch').value.trim().toLocaleLowerCase('vi');
    const visible=titleCatalog.filter(t=>!query||`${t.display_name_vi} ${t.code} ${t.realm_ordinal||''}`.toLocaleLowerCase('vi').includes(query));
    $('#gcTitleList').innerHTML=visible.map(t=>`<label class="gift-title-option ${selectedTitles.has(t.code)?'selected':''}" title="${esc(`${t.display_name_vi} · ${t.code}`)}"><input data-gc-title="${esc(t.code)}" type="checkbox" ${selectedTitles.has(t.code)?'checked':''}><span class="gift-title-art">${titleArtworkUrl(t)?`<img src="${esc(titleArtworkUrl(t))}" alt="">`:'Ảnh chưa có'}</span><span><b>${esc(t.display_name_vi)}</b><small>${t.realm_ordinal?`Bậc ${t.realm_ordinal}`:esc(t.source_type)} · ${esc(t.code)}</small></span></label>`).join('')||'<p class="muted">Không tìm thấy danh hiệu.</p>';
    $$('[data-gc-title]').forEach(input=>input.onchange=()=>{input.checked?selectedTitles.add(input.dataset.gcTitle):selectedTitles.delete(input.dataset.gcTitle);paintTitlePicker();});
    const names=[...selectedTitles].map(code=>titleCatalog.find(t=>t.code===code)?.display_name_vi||code);
    $('#gcTitleSummary').textContent=names.length?`Đã chọn ${names.length}: ${names.slice(0,3).join(', ')}${names.length>3?` +${names.length-3} khác`:''}`:'Chưa chọn danh hiệu.';
    const target=$('#gcArtworkTitle'),previous=target.value;
    target.innerHTML=[...selectedTitles].map(code=>`<option value="${esc(code)}">${esc(titleCatalog.find(t=>t.code===code)?.display_name_vi||code)}</option>`).join('')||'<option value="">Chọn danh hiệu trước</option>';
    if(selectedTitles.has(previous))target.value=previous;
    buildReward();
  };
  $('#gcTitleSearch').oninput=paintTitlePicker;
  ['#gcGold','#gcGems','#gcJade','#gcSp','#gcWood','#gcFood','#gcOre','#gcEssence','#gcClan','#gcSeason'].forEach(selector=>$(selector).oninput=buildReward);
  let previewUrl;
  $('#gcArtworkFile').onchange=()=>{if(previewUrl)URL.revokeObjectURL(previewUrl);const file=$('#gcArtworkFile').files[0],preview=$('#gcArtworkPreview');preview.hidden=!file;if(file){previewUrl=URL.createObjectURL(file);preview.src=previewUrl;}};
  $('#gcArtworkUpload').onclick=async()=>{const code=$('#gcArtworkTitle').value,file=$('#gcArtworkFile').files[0];if(!code||!selectedTitles.has(code)){alert('Chọn danh hiệu trước.');return;}if(!file){alert('Chọn ảnh trước.');return;}const headers=writeHeaders(false);if(!headers)return;const body=new FormData();body.append('file',file);try{const result=await api(`/api/content-media/title/${encodeURIComponent(code)}/image`,{method:'POST',headers,body});const title=titleCatalog.find(t=>t.code===code);if(title)title.artwork_url=result.image_url;$('#gcArtworkFile').value='';$('#gcArtworkPreview').hidden=true;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;paintTitlePicker();showNotice(`Đã cập nhật ảnh danh hiệu ${title?.display_name_vi||code}.`,'warning');}catch(error){alert(error.message);}};
  paintTitlePicker();
  $('#gcSave').onclick=async()=>{let reward;try{reward=buildReward();}catch(e){alert(e.message||'Phần thưởng không hợp lệ.');return;}const minLevel=Number($('#gcMinLevel').value||1),maxLevel=$('#gcMaxLevel').value?Number($('#gcMaxLevel').value):null,minFloor=Number($('#gcMinFloor').value||1);if(!Number.isSafeInteger(minLevel)||!Number.isSafeInteger(minFloor)||(maxLevel!==null&&!Number.isSafeInteger(maxLevel))||minLevel<1||minFloor<1||(maxLevel!==null&&maxLevel<minLevel)){alert('Điều kiện level/floor không hợp lệ.');return;}const elig={min_account_level:minLevel,min_exploration_floor:minFloor,account_status:$('#gcAccountStatus').value};if(maxLevel!==null)elig.max_account_level=maxLevel;const code=$('#gcCode').value;const payload={code,display_name:code,description:$('#gcDesc').value,status:$('#gcStatus').value,max_redemptions:$('#gcMax').value?Number($('#gcMax').value):null,per_player_limit:Number($('#gcPer').value||1),tags:[],reward_bundle:reward,eligibility_json:elig};const h=writeHeaders(true);if(!h)return;try{await api(creating?'/api/giftcodes':`/api/giftcodes/${encodeURIComponent(g.id)}`,{method:creating?'POST':'PATCH',headers:h,body:JSON.stringify(payload)});showNotice(creating?'Đã tạo giftcode với đầy đủ phần thưởng.':'Đã cập nhật toàn bộ phần thưởng giftcode.','warning');closeDrawer();await renderGiftcodes();}catch(e){alert(e.message);}};
  if(!creating){$('#gcArchive').onclick=async()=>{if(!confirm(`Archive ${g.code}?`))return;const h=writeHeaders(false);if(!h)return;try{await api(`/api/giftcodes/${encodeURIComponent(g.id)}`,{method:'DELETE',headers:h});closeDrawer();await renderGiftcodes();}catch(e){alert(e.message);}};$('#gcRedemptions').onclick=async()=>{const r=await api(`/api/giftcodes/${encodeURIComponent(g.id)}/redemptions`);openDrawer(`${g.code} • Redemptions`,'GIFT CODE / HISTORY',r.rows.length?supportRowsTable(r.rows,['player_name','player_id','status','redeemed_at','granted_at','error_code']):'<div class="empty">Chưa có redemption.</div>');};}
}

function openGiftcodeTester(){
  openDrawer('Test Giftcode','GIFT CODE / VALIDATION PREVIEW',`<div class="card card-pad"><div class="field"><label>Code</label><input id="gcTestCode" placeholder="LK-..."></div><div class="field"><label>Player ID (optional)</label><input id="gcTestPlayer" placeholder="UUID để test per-player/min level"></div><button id="gcTestRun" class="btn btn-primary">Validate</button><pre id="gcTestResult" class="json-block">Chưa chạy.</pre></div>`);$('#gcTestRun').onclick=async()=>{try{const r=await api('/api/giftcodes/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('#gcTestCode').value,player_id:$('#gcTestPlayer').value||null})});$('#gcTestResult').textContent=JSON.stringify(r,null,2);}catch(e){$('#gcTestResult').textContent=e.message;}};
}



async function resourceImageUpload(code){
  const input=document.createElement('input'); input.type='file'; input.accept='image/png,image/jpeg,image/webp,image/gif';
  input.onchange=async()=>{
    const file=input.files?.[0]; if(!file)return;
    const h=writeHeaders(false); if(!h)return;
    const fd=new FormData();fd.append('file',file);
    try{
      await api(`/api/resource-assets/${encodeURIComponent(code)}/image`,{method:'POST',headers:h,body:fd});
      showNotice(`Đã cập nhật ảnh ${code}. Bot/Web dùng cùng shared media.`, 'warning');
      app.resourceAssets=null; await renderMaterials();
    }catch(e){alert(e.message);}
  };
  input.click();
}

async function resourceImageDelete(code){
  if(!confirm(`Xóa ảnh hiện tại của ${code}?`))return;
  const h=writeHeaders(false);if(!h)return;
  try{
    await api(`/api/resource-assets/${encodeURIComponent(code)}/image`,{method:'DELETE',headers:h});
    showNotice(`Đã xóa ảnh ${code}.`,'warning'); app.resourceAssets=null; await renderMaterials();
  }catch(e){alert(e.message);}
}

async function consumableImageUpload(code){
  const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp,image/gif';
  input.onchange=async()=>{const file=input.files?.[0];if(!file)return;const h=writeHeaders(false);if(!h)return;const fd=new FormData();fd.append('file',file);
    try{await api(`/api/consumable-assets/${encodeURIComponent(code)}/image`,{method:'POST',headers:h,body:fd});showNotice(`Đã cập nhật ảnh ${code} cho mọi phiên bản. Bot dùng ngay shared media.`, 'warning');await renderMaterials();}catch(e){alert(e.message);}};
  input.click();
}

async function consumableImageDelete(code){
  if(!confirm(`Xóa ảnh hiện tại của ${code} trên mọi phiên bản?`))return;const h=writeHeaders(false);if(!h)return;
  try{await api(`/api/consumable-assets/${encodeURIComponent(code)}/image`,{method:'DELETE',headers:h});showNotice(`Đã xóa ảnh ${code}.`,'warning');await renderMaterials();}catch(e){alert(e.message);}
}

function consumableCard(r){
  const img=r.image_url?`<img src="${esc(r.image_url)}" alt="${esc(r.code)}">`:'<span>◈</span>';
  return `<div class="card material-card"><div class="material-art">${img}</div><div class="material-info"><div class="material-tags"><span class="badge">Vật phẩm tiêu hao</span></div><h3>${esc(r.display_name_vi||r.code)}</h3><div class="code advanced-only">${esc(r.code)}</div><p>Ảnh nhỏ dùng chung cho Túi đồ và Admin.</p></div><div class="material-actions"><button class="btn btn-primary btn-small" data-cons-upload="${esc(r.code)}">${r.image_url?'Thay ảnh':'＋ Ảnh'}</button><button class="btn btn-secondary btn-small" data-cons-delete="${esc(r.code)}" ${r.image_url?'':'disabled'}>Xóa ảnh</button></div></div>`;
}

function resourceCard(r){
  const img=r.image_url?`<img src="${esc(r.image_url)}" alt="${esc(r.code)}">`:`<span>${r.material_family==='EQUIPMENT_ORE'?'⛏':'◆'}</span>`;
  const tags=r.material_family==='EQUIPMENT_ORE'
    ?`${rarityBadge(r.target_rarity)}<span class="badge">${esc(r.target_slot)}</span>`
    :`<span class="badge">${esc(r.asset_type)}</span>`;
  return `<div class="card material-card" data-material-code="${esc(r.code)}">
    <div class="material-art">${img}</div>
    <div class="material-info">
      <div class="material-tags">${tags}</div>
      <h3>${esc(r.display_name_vi||r.code)}</h3>
      <div class="code advanced-only">${esc(r.code)}</div>
      ${r.material_family==='EQUIPMENT_ORE'?`<p>${esc(r.purpose_vi||'Nguyên liệu chế tạo chuyên dụng.')}</p>`:''}
    </div>
    <div class="material-actions">
      <button class="btn btn-primary btn-small" data-res-upload="${esc(r.code)}">${r.image_url?'Thay ảnh':'＋ Ảnh'}</button>
      <button class="btn btn-secondary btn-small" data-res-delete="${esc(r.code)}" ${r.image_url?'':'disabled'}>Xóa ảnh</button>
    </div>
  </div>`;
}

async function renderSystemShop(){
  await ensureCore();setPageMeta('Cửa hàng hệ thống','HÀNG BÁN');hideNotice();
  let data;try{data=await api('/api/system-shop');}catch(error){pageEl.innerHTML=`<div class="card">Chưa tải được cửa hàng: ${esc(error.message)}</div>`;return;}
  const kindNames={ASSET:'Tài nguyên',CONSUMABLE:'Tiêu hao',EQUIPMENT:'Trang bị'};
  const active=data.offers.filter(x=>x.enabled).length, hidden=data.offers.length-active, low=data.offers.filter(x=>x.enabled&&x.stock!==null&&x.stock<=5).length;
  pageEl.innerHTML=`<div class="card shop-hero"><div><div class="eyebrow">CỬA HÀNG HỆ THỐNG</div><h2>Quản lý hàng bán</h2><p>Thay đổi tại đây được bot đọc trực tiếp. Người chơi dùng <code>!shop</code> hoặc <code>!cuahang</code>.</p></div><button class="btn btn-primary" id="newShopOffer">＋ Thêm hàng bán</button></div>
  <div class="shop-kpis"><div class="card"><b>${data.offers.length}</b><span>Tổng mặt hàng</span></div><div class="card"><b>${active}</b><span>Đang bán</span></div><div class="card"><b>${hidden}</b><span>Tạm ẩn</span></div><div class="card ${low?'shop-warning':''}"><b>${low}</b><span>Sắp hết hàng</span></div></div>
  <div id="shopEditor" class="card" hidden></div>
  <div class="card"><div class="shop-toolbar"><input id="shopSearch" type="search" placeholder="Tìm tên hoặc mã vật phẩm"><select id="shopStatus"><option value="all">Tất cả trạng thái</option><option value="active">Đang bán</option><option value="hidden">Tạm ẩn</option><option value="low">Sắp hết hàng</option></select></div><div class="table-wrap"><table><thead><tr><th>Hàng bán</th><th>Loại</th><th>Số lượng</th><th>Giá</th><th>Tồn kho</th><th>Trạng thái</th><th></th></tr></thead><tbody id="shopRows">${data.offers.map((offer,index)=>`<tr data-shop-row data-search="${esc((offer.display_name+' '+offer.reward_code).toLowerCase())}" data-status="${!offer.enabled?'hidden':offer.stock!==null&&offer.stock<=5?'low':'active'}"><td><b>${esc(offer.display_name)}</b><small>${esc(offer.reward_code)}</small></td><td>${esc(kindNames[offer.reward_kind]||offer.reward_kind)}</td><td>${fmt(offer.quantity)}</td><td>${fmt(offer.price)} ${esc(data.currencies.find(c=>c.code===offer.price_asset)?.name||offer.price_asset)}</td><td>${offer.stock===null?'Không giới hạn':fmt(offer.stock)}</td><td><span class="shop-state ${offer.enabled?'is-active':'is-hidden'}">${offer.enabled?'Đang bán':'Tạm ẩn'}</span></td><td><button class="btn" data-edit-shop="${index}">Chỉnh sửa</button></td></tr>`).join('')||'<tr><td colspan="7">Chưa có hàng bán. Nhấn Thêm hàng bán để tạo.</td></tr>'}</tbody></table></div></div>`;
  const filterRows=()=>{const query=$('#shopSearch').value.trim().toLowerCase(),status=$('#shopStatus').value;$$('[data-shop-row]').forEach(row=>{const statusMatch=status==='all'||row.dataset.status===status||(status==='active'&&row.dataset.status==='low');row.hidden=!row.dataset.search.includes(query)||!statusMatch;});};
  $('#shopSearch').oninput=filterRows;$('#shopStatus').onchange=filterRows;
  const edit=(offer)=>{
    const panel=$('#shopEditor');panel.hidden=false;
    const selected=offer?data.choices.findIndex(c=>c.kind===offer.reward_kind&&c.code===offer.reward_code&&String(c.config)===String(offer.item_config_version_id)):-1;
    panel.innerHTML=`<div class="shop-editor-title"><div><div class="eyebrow">${offer?'CHỈNH SỬA':'MẶT HÀNG MỚI'}</div><h3>${offer?esc(offer.display_name):'Thêm hàng bán'}</h3></div><button class="btn" id="closeShopEditor" type="button">Đóng</button></div><form id="shopForm"><label>Vật phẩm<select id="shopChoice" required><option value="">Chọn vật phẩm</option>${data.choices.map((c,i)=>`<option value="${i}" ${i===selected?'selected':''}>${esc(kindNames[c.kind])} · ${esc(c.name)}${c.rarity?' · '+esc(RARITY_VI[c.rarity]||c.rarity):''}</option>`).join('')}</select></label><label>Tên hiển thị<input id="shopName" maxlength="160" required value="${esc(offer?.display_name||'')}"></label><label>Số lượng mỗi gói<input id="shopQuantity" type="number" min="1" max="1000000" step="1" required value="${offer?.quantity||1}"></label><label>Cấp trang bị<input id="shopLevel" type="number" min="1" max="1000000" step="1" required value="${offer?.item_level||1}"></label><label>Tiền thanh toán<select id="shopCurrency">${data.currencies.map(c=>`<option value="${esc(c.code)}" ${c.code===(offer?.price_asset||'GOLD')?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label>Giá mỗi gói<input id="shopPrice" type="number" min="1" max="1000000000000" step="1" required value="${offer?.price||1}"></label><label>Tồn kho <small>Để trống nếu không giới hạn</small><input id="shopStock" type="number" min="0" max="1000000000" step="1" value="${offer?.stock??''}"></label><label class="shop-checkbox"><input id="shopEnabled" type="checkbox" ${offer?.enabled?'checked':''}><span><b>Đang bán</b><small>Tắt để ẩn khỏi bot nhưng vẫn giữ cấu hình.</small></span></label><button class="btn btn-primary" type="submit">Lưu hàng bán</button></form>`;
    $('#closeShopEditor').onclick=()=>{panel.hidden=true;};
    $('#shopChoice').onchange=()=>{const choice=data.choices[Number($('#shopChoice').value)];if(!choice)return;$('#shopName').value=choice.name;$('#shopQuantity').value=1;$('#shopQuantity').disabled=choice.kind==='EQUIPMENT';$('#shopLevel').disabled=choice.kind!=='EQUIPMENT';};
    $('#shopForm').onsubmit=async(event)=>{event.preventDefault();if($('#shopChoice').value==='')return;const choice=data.choices[Number($('#shopChoice').value)],headers=writeHeaders(true);if(!headers)return;const button=event.currentTarget.querySelector('button');button.disabled=true;try{await api('/api/system-shop',{method:'POST',headers,body:JSON.stringify({id:offer?.id,version:offer?.version,display_name:$('#shopName').value,reward_kind:choice.kind,reward_code:choice.code,item_config_version_id:choice.config,quantity:Number($('#shopQuantity').value),item_level:Number($('#shopLevel').value),price_asset:$('#shopCurrency').value,price:Number($('#shopPrice').value),stock:$('#shopStock').value===''?null:Number($('#shopStock').value),enabled:$('#shopEnabled').checked})});await renderSystemShop();showNotice('Đã lưu hàng bán. Bot bản mới đọc trực tiếp cấu hình này.','warning');}catch(error){alert(error.message);button.disabled=false;}};
    panel.scrollIntoView({behavior:'smooth',block:'start'});
  };
  $('#newShopOffer').onclick=()=>edit(null);$$('[data-edit-shop]').forEach(button=>button.onclick=()=>edit(data.offers[Number(button.dataset.editShop)]));
}

async function renderMaterials(){
  await ensureCore();
  setPageMeta('Tài nguyên & Ore','ADMIN / STATIC ASSETS'); hideNotice();
  let data,consumableData,dropData,itemDropData;
  try{[data,consumableData,dropData,itemDropData]=await Promise.all([api('/api/resource-assets?include_ores=true'),api('/api/consumable-assets'),api('/api/gameplay/drop-rates'),api('/api/gameplay/item-drop-rates?slot=HELM&rarity=COMMON')]);}
  catch(e){pageEl.innerHTML=`<div class="card empty"><b>Chưa sẵn sàng.</b><br>${esc(e.message)}<br><br>Chạy <code>sql\\80_v70_equipment_ore_materials.sql</code> trong DBeaver trước.</div>`;return;}
  app.resourceAssets=data;
  const rows=data.rows||[], core=rows.filter(x=>!x.material_family), ores=rows.filter(x=>x.material_family==='EQUIPMENT_ORE'), consumables=consumableData.rows||[];
  pageEl.innerHTML=`
    <div class="card media-hero material-hero">
      <div><div class="eyebrow">TÀI NGUYÊN & TỶ LỆ RƠI</div><h2>Tài nguyên, tăng tốc và Ore chế tạo</h2>
      <p>Quản lý icon nhỏ dùng chung cho Bot/Web và kiểm tra tỷ lệ rơi đang chạy. Mã kỹ thuật chỉ hiện trong chế độ nâng cao.</p></div>
      <div class="domain-kpis"><div><b>${core.length}</b><span>Tài nguyên nền</span></div><div><b>${ores.length}</b><span>Ore / 90</span></div><div><b>${rows.filter(x=>x.image_url).length}</b><span>Đã có ảnh</span></div></div>
    </div>
    ${ores.length!==90?`<div class="inline-warning"><b>DB chưa đủ 90 ore (bao gồm PET).</b> Chạy <code>sql\\80_v70_equipment_ore_materials.sql</code> trong DBeaver trên <code>lost_kingsland_v4_reconciled</code>.</div>`:''}
    <div class="toolbar material-toolbar">
      <div class="search"><input id="matSearch" placeholder="Tìm code/tên nguyên liệu…"></div>
      <select id="matRarity"><option value="">Tất cả rarity</option>${RARITY_ORDER.map(r=>`<option>${r}</option>`).join('')}</select>
      <select id="matSlot"><option value="">Tất cả slot</option>${['HELM','CHEST','SHOULDER','AMULET','BOOTS','RING','OFF_HAND','WEAPON','PET'].map(x=>`<option>${x}</option>`).join('')}</select>
      <button id="seedResourceIcons" class="btn btn-primary">⚡ Gắn demo 100 icon</button>
    </div>
    <div class="section-head"><div><div class="section-title">Tài nguyên nền</div><div class="section-sub">Vàng, Gem, Ngọc, Gỗ, Quặng, Lương thực, Tinh hoa, Linh khí, Điểm kỹ năng, Dấu ấn Clan và Xu mùa giải.</div></div></div>
    <div id="coreResourceGrid" class="material-grid compact-material-grid">${core.map(resourceCard).join('')}</div>
    <div class="section-head"><div><div class="section-title">Tỷ lệ mọi tài nguyên từ quái</div><div class="section-sub">Vàng, Gỗ, Lương thực, Quặng, Tăng tốc và Tinh hoa dùng chung một lượt quay. Tổng tối đa 100%; phần còn thiếu là không rơi tài nguyên. Trang bị và Điểm kỹ năng vẫn chắc chắn.</div></div><div id="resourceRateTotal" class="badge on">${esc(fmtAmount(Number(dropData.resource_total_bps||0)/100))}%</div></div>
    <div class="toolbar material-toolbar"><button id="saveResourceRates" class="btn btn-primary" ${app.meta.mode==='live'&&app.meta.write_enabled?'':'disabled'}>Lưu tỷ lệ tài nguyên</button></div>
    <div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Vật phẩm</th><th>Tỷ lệ rơi</th><th>Tối thiểu</th><th>Tối đa</th></tr></thead><tbody>${(dropData.resources||[]).map(r=>`<tr><td>${esc(r.icon_glyph||'◆')} <b>${esc(r.display_name_vi)}</b><div class="code advanced-only">${esc(r.asset_code)}</div></td><td><div class="rate-input"><input data-resource-rate="${esc(r.asset_code)}" type="number" min="0" max="100" step="0.01" value="${esc(r.chance_percent)}"><span>%</span></div></td><td><input class="compact-number" data-resource-min="${esc(r.asset_code)}" type="number" min="0" step="1" value="${esc(r.minimum_quantity)}"></td><td><input class="compact-number" data-resource-max="${esc(r.asset_code)}" type="number" min="0" step="1" value="${esc(r.maximum_quantity)}"></td></tr>`).join('')||'<tr><td colspan="4">Chưa có cấu hình tỷ lệ.</td></tr>'}</tbody></table></div></div>
    <div class="section-head"><div><div class="section-title">Tỷ lệ Ore theo phẩm chất</div><div class="section-sub">Rate thấp dần theo phẩm chất để giữ giá trị chế tạo.</div></div></div>
    <div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Phẩm chất</th><th>Tỷ lệ</th><th>Số lượng</th><th>Cần để chế tạo</th></tr></thead><tbody>${(dropData.specialized_ores||[]).map(r=>`<tr><td>${rarityBadge(r.rarity)}</td><td><b>${esc(fmtAmount(r.chance_percent))}%</b></td><td>${esc(fmt(r.minimum_quantity))}${Number(r.maximum_quantity)!==Number(r.minimum_quantity)?` – ${esc(fmt(r.maximum_quantity))}`:''}</td><td>${esc(fmt(r.craft_cost))}</td></tr>`).join('')}</tbody></table></div></div>
    <div class="section-head"><div><div class="section-title">Tỷ lệ từng trang bị</div><div class="section-sub">Chọn vị trí và phẩm chất. Tổng pool bắt buộc đúng 100%; bot dùng rate này ngay cho lần rơi mới.</div></div><div id="itemRateTotal" class="badge on">100%</div></div>
    <div class="toolbar material-toolbar"><select id="itemRateSlot">${Object.entries(SLOT_VI).map(([code,label])=>`<option value="${code}">${esc(label)}</option>`).join('')}</select><select id="itemRateRarity">${RARITY_ORDER.map(code=>`<option value="${code}">${esc(RARITY_VI[code])}</option>`).join('')}</select><button id="saveItemRates" class="btn btn-primary" ${app.meta.mode==='live'&&app.meta.write_enabled?'':'disabled'}>Lưu tỷ lệ</button></div>
    <div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Vật phẩm</th><th>Tỷ lệ rơi</th></tr></thead><tbody id="itemRateRows"></tbody></table></div></div>
    <div class="section-head"><div><div class="section-title">Vật phẩm tiêu hao</div><div class="section-sub">Bot hiển thị ảnh nhỏ này trong túi. Thay ảnh tại đây sẽ áp dụng cho mọi phiên bản cùng mã vật phẩm.</div></div><div class="badge">${consumables.filter(x=>x.image_url).length} / ${consumables.length} có ảnh</div></div>
    <div id="consumableGrid" class="material-grid compact-material-grid">${consumables.map(consumableCard).join('')}</div>
    <div class="section-head"><div><div class="section-title">90 Ore chuyên dụng</div><div class="section-sub">Mỗi ore chỉ map đến đúng slot + rarity mục tiêu. Ảnh demo nhỏ kiểu emote, không phải artwork lớn.</div></div><div id="matCount" class="badge">${ores.length}</div></div>
    <div id="oreGrid" class="material-grid"></div>`;
  const paintItemRates=()=>{
    const items=itemDropData.items||[];
    $('#itemRateRows').innerHTML=items.map(item=>`<tr><td><div class="rate-item">${item.image_url?`<img src="${esc(item.image_url)}" alt="">`:'<span>◈</span>'}<div><b>${esc(item.display_name_vi||item.item_code)}</b><div class="code advanced-only">${esc(item.item_code)}</div></div></div></td><td><div class="rate-input"><input data-item-rate="${esc(item.item_code)}" type="number" min="0" max="100" step="0.01" value="${esc(item.rate_percent)}"><span>%</span></div></td></tr>`).join('')||'<tr><td colspan="2">Pool này chưa có dữ liệu tỷ lệ.</td></tr>';
    const updateTotal=()=>{const total=$$('[data-item-rate]').reduce((sum,input)=>sum+Number(input.value||0),0),valid=Math.abs(total-100)<0.000001;$('#itemRateTotal').textContent=`${fmtAmount(total)}%`;$('#itemRateTotal').classList.toggle('on',valid);$('#itemRateTotal').classList.toggle('off',!valid);if(app.meta.mode==='live'&&app.meta.write_enabled)$('#saveItemRates').disabled=!valid;};
    $$('[data-item-rate]').forEach(input=>input.oninput=updateTotal);updateTotal();applyAdvancedMode();
  };
  const updateResourceTotal=()=>{const total=$$('[data-resource-rate]').reduce((sum,input)=>sum+Number(input.value||0),0),valid=total<=100.000001;$('#resourceRateTotal').textContent=`${fmtAmount(total)}%`;$('#resourceRateTotal').classList.toggle('on',valid);$('#resourceRateTotal').classList.toggle('off',!valid);if(app.meta.mode==='live'&&app.meta.write_enabled)$('#saveResourceRates').disabled=!valid;};
  $$('[data-resource-rate]').forEach(input=>input.oninput=updateResourceTotal);updateResourceTotal();
  $('#saveResourceRates').onclick=async()=>{const items=(dropData.resources||[]).map(row=>({asset_code:row.asset_code,rate_percent:Number($(`[data-resource-rate="${row.asset_code}"]`).value),minimum_quantity:Number($(`[data-resource-min="${row.asset_code}"]`).value),maximum_quantity:Number($(`[data-resource-max="${row.asset_code}"]`).value)}));const total=items.reduce((sum,item)=>sum+item.rate_percent,0);if(total>100.000001){alert(`Tổng tỷ lệ không được vượt 100%. Hiện tại: ${fmtAmount(total)}%.`);return;}if(items.some(item=>!Number.isInteger(item.minimum_quantity)||!Number.isInteger(item.maximum_quantity)||item.minimum_quantity<0||item.maximum_quantity<item.minimum_quantity)){alert('Số lượng phải là số nguyên không âm; tối đa không nhỏ hơn tối thiểu.');return;}const headers=writeHeaders(true);if(!headers)return;const button=$('#saveResourceRates');button.disabled=true;button.textContent='Đang lưu…';try{await api('/api/gameplay/drop-rates',{method:'PUT',headers,body:JSON.stringify({config:dropData.config,items})});showNotice('Đã lưu tỷ lệ Vàng, Gỗ, Lương thực, Quặng, Tăng tốc và Tinh hoa. Bot áp dụng từ trận mới.','warning');await renderMaterials();}catch(e){alert(e.message);}finally{if(button.isConnected){button.textContent='Lưu tỷ lệ tài nguyên';button.disabled=false;}}};
  const loadItemRates=async()=>{const slot=$('#itemRateSlot').value,rarity=$('#itemRateRarity').value;itemDropData=await api(`/api/gameplay/item-drop-rates?slot=${encodeURIComponent(slot)}&rarity=${encodeURIComponent(rarity)}`);paintItemRates();};
  $('#itemRateSlot').onchange=loadItemRates;$('#itemRateRarity').onchange=loadItemRates;
  $('#saveItemRates').onclick=async()=>{const items=$$('[data-item-rate]').map(input=>({item_code:input.dataset.itemRate,rate_percent:Number(input.value)})),total=items.reduce((sum,item)=>sum+item.rate_percent,0);if(Math.abs(total-100)>0.000001){alert(`Tổng tỷ lệ phải đúng 100%. Hiện tại: ${fmtAmount(total)}%.`);return;}const headers=writeHeaders(true);if(!headers)return;const button=$('#saveItemRates');button.disabled=true;button.textContent='Đang lưu…';try{await api('/api/gameplay/item-drop-rates',{method:'PUT',headers,body:JSON.stringify({config:itemDropData.config,slot:$('#itemRateSlot').value,rarity:$('#itemRateRarity').value,items})});showNotice('Đã lưu pool 100%. Bot áp dụng cho lần rơi trang bị mới.','warning');await loadItemRates();}catch(e){alert(e.message);}finally{button.textContent='Lưu tỷ lệ';}};
  paintItemRates();
  const wheelPanel=document.createElement('section');
  wheelPanel.className='card';
  pageEl.appendChild(wheelPanel);
  try {
    const wheelRates=await api('/api/gameplay/wheel-rates');
    wheelPanel.innerHTML=`<h2>Tỷ lệ phần thưởng Wheel</h2><p>Tổng đúng 100%. Bảo đảm nhân vật có thể thay thế kết quả thông thường. Áp dụng sau khi bot đã được triển khai bản hỗ trợ cấu hình này.</p><div class="table-wrap"><table><thead><tr><th>Nhóm phần thưởng</th><th>Tỷ lệ</th></tr></thead><tbody>${wheelRates.items.map(item=>`<tr><td>${esc(item.name)}</td><td><input type="number" min="0" max="100" step="1" data-wheel-rate="${esc(item.category)}" value="${esc(item.rate_percent)}"> %</td></tr>`).join('')}</tbody></table></div><p data-wheel-total></p><button class="btn btn-primary" data-wheel-save>Lưu tỷ lệ Wheel</button>`;
    const inputs=[...wheelPanel.querySelectorAll('[data-wheel-rate]')], save=wheelPanel.querySelector('[data-wheel-save]');
    const validate=()=>{const values=inputs.map(input=>Number(input.value)),total=values.reduce((sum,value)=>sum+value,0);wheelPanel.querySelector('[data-wheel-total]').textContent=`Tổng: ${total}% / 100%`;save.disabled=!(app.meta.mode==='live'&&app.meta.write_enabled&&total===100&&values.every(value=>Number.isInteger(value)&&value>=0&&value<=100));};
    inputs.forEach(input=>input.addEventListener('input',validate));validate();
    save.onclick=async()=>{const headers=writeHeaders(true);if(!headers)return;save.disabled=true;try{await api('/api/gameplay/wheel-rates',{method:'PUT',headers,body:JSON.stringify({items:inputs.map(input=>({category:input.dataset.wheelRate,rate_percent:Number(input.value)}))})});showNotice('Đã lưu tỷ lệ Wheel. Các ván đã có kết quả không bị thay đổi.','warning');}catch(error){alert(error.message);}finally{validate();}};
  } catch(error) { wheelPanel.textContent=`Chưa tải được tỷ lệ Wheel: ${error.message}`; }
  const paint=()=>{
    const q=$('#matSearch').value.trim().toLowerCase(), rarity=$('#matRarity').value, slot=$('#matSlot').value;
    const list=ores.filter(r=>(!rarity||r.target_rarity===rarity)&&(!slot||r.target_slot===slot)&&(!q||`${r.code} ${r.display_name_vi}`.toLowerCase().includes(q)));
    $('#oreGrid').innerHTML=list.map(resourceCard).join('')||'<div class="card empty">Không có kết quả.</div>'; $('#matCount').textContent=`${list.length} / ${ores.length}`; wire();applyAdvancedMode();
  };
  const wire=()=>{
    $$('[data-res-upload]').forEach(b=>b.onclick=()=>resourceImageUpload(b.dataset.resUpload));
    $$('[data-res-delete]').forEach(b=>b.onclick=()=>resourceImageDelete(b.dataset.resDelete));
    $$('[data-cons-upload]').forEach(b=>b.onclick=()=>consumableImageUpload(b.dataset.consUpload));
    $$('[data-cons-delete]').forEach(b=>b.onclick=()=>consumableImageDelete(b.dataset.consDelete));
  };
  $('#matSearch').oninput=paint;$('#matRarity').onchange=paint;$('#matSlot').onchange=paint;
  $('#seedResourceIcons').onclick=async()=>{
    if(ores.length!==90){alert('DB chưa đủ 90 ore (bao gồm PET). Hãy chạy sql/80_v70_equipment_ore_materials.sql trong DBeaver trước.');return;}
    const h=writeHeaders(false);if(!h)return;
    $('#seedResourceIcons').disabled=true;$('#seedResourceIcons').textContent='Đang tải + dựng icon…';
    try{
      const r=await api('/api/resource-assets/seed-demo-icons',{method:'POST',headers:h});
      if(!r.ok) throw new Error(r.output||'Seeder failed');
      showNotice('Đã gắn icon demo vào PostgreSQL shared media. Bot/Web có thể dùng cùng asset.','warning'); app.resourceAssets=null; await renderMaterials();
    }catch(e){alert(e.message);}finally{const b=$('#seedResourceIcons');if(b){b.disabled=false;b.textContent='⚡ Gắn demo 100 icon';}}
  };
  wire();paint();applyAdvancedMode();
}

async function renderDiscordProfile(){
  titleEl.textContent='Hồ sơ Discord';eyebrowEl.textContent='DISCORD / PUBLIC PROFILE';
  const locale='vi-VN',data=await api(`/api/discord-profile?locale=${locale}`);
  const labels={card_title:'Tiêu đề hồ sơ',intro_text:'Dòng huy hiệu',divider_text:'Đường phân cách',identity_heading:'Nhóm thân phận',progression_heading:'Nhóm tu luyện',combat_heading:'Nhóm sức mạnh',assets_heading:'Nhóm tài sản',equipment_heading:'Nhóm trang bị',race_label:'Chủng tộc',path_label:'Con đường',affinity_label:'Thuộc tính',realm_label:'Cảnh giới',stage_label:'Bậc',level_label:'Cấp độ',xp_label:'Kinh nghiệm',cultivation_qi_label:'Linh khí',cultivation_progress_label:'Tiến độ tu luyện',clan_label:'Bang hội',clan_role_label:'Vai trò Clan',power_label:'Power',vitality_label:'Sinh lực',martial_label:'Võ lực',mystic_label:'Pháp lực',armor_label:'Giáp',ward_label:'Kháng phép',speed_label:'Tốc độ',crit_label:'Chí mạng',penetration_label:'Xuyên giáp',empty_equipment_label:'Trang bị trống',footer_text:'Chân thẻ'};
  const keys=Object.keys(labels);
  pageEl.innerHTML=`<div class="domain-hero card card-pad"><div><div class="eyebrow">BOT + ADMIN + DATABASE</div><h2>Trình chỉnh hồ sơ công khai</h2><p class="muted">Chỉ sửa câu chữ và nhãn hiển thị. Tên, cảnh giới, cấp, Power, chỉ số, trang bị và tài sản luôn đọc trực tiếp từ gameplay DB. Placeholder hỗ trợ: <b>{name}</b>, <b>{mention}</b>, <b>{level}</b>, <b>{realm}</b>, <b>{stage}</b>, <b>{clan}</b>, <b>{clan_role}</b>.</p></div></div>
    <div class="card card-pad"><div class="form-grid">${keys.map(k=>`<div class="field"><label>${esc(labels[k])}</label><input data-profile-field="${k}" value="${esc(data[k])}"></div>`).join('')}</div>
    <label class="check-row"><input id="profileShowAssets" type="checkbox" ${data.show_assets?'checked':''}> Hiện Vàng, Gem và Ngọc trên hồ sơ</label>
    <label class="check-row"><input id="profileShowEquipment" type="checkbox" ${data.show_equipment?'checked':''}> Hiện trang bị đang mặc</label>
    <div class="drawer-actions"><button id="saveDiscordProfile" class="btn btn-primary">Lưu và áp dụng ngay cho Bot</button></div></div>`;
  $('#saveDiscordProfile').onclick=async()=>{const headers=writeHeaders(true);if(!headers)return;const payload={show_assets:$('#profileShowAssets').checked,show_equipment:$('#profileShowEquipment').checked};$$('[data-profile-field]').forEach(input=>payload[input.dataset.profileField]=input.value);const button=$('#saveDiscordProfile');button.disabled=true;button.textContent='Đang lưu…';try{await api(`/api/discord-profile?locale=${locale}`,{method:'PATCH',headers,body:JSON.stringify(payload)});showNotice('Đã cập nhật hồ sơ. Lần gõ !profile tiếp theo dùng nội dung mới.','warning');}catch(e){alert(e.message);}finally{button.disabled=false;button.textContent='Lưu và áp dụng ngay cho Bot';}};
}

async function renderTopup(){
  const data=await api('/api/topup');
  pageEl.innerHTML=`<div class="card shop-hero"><div><div class="eyebrow">PAYOS / VIETQR</div><h2>Thanh toán & Nạp tiền</h2><p>Chỉnh nội dung hiển thị cho <code>!nap</code>, quản lý gói và đối soát đơn. Không có nút tự đánh dấu đã thanh toán.</p></div></div>
  <div class="card"><h3>Giao diện Discord</h3><form id="topupUi"><label>Tiêu đề<input id="topupTitle" maxlength="100" value="${esc(data.ui.title)}"></label><label>Hướng dẫn<textarea id="topupInstructions" maxlength="1000">${esc(data.ui.instructions)}</textarea></label><label>Chân trang<input id="topupFooter" maxlength="300" value="${esc(data.ui.footer)}"></label><button class="btn btn-primary">Lưu giao diện</button></form></div>
  <div class="card"><h3>Gói nạp</h3><div class="table-wrap"><table><thead><tr><th>Mã</th><th>VND</th><th>Phần thưởng</th><th>Thưởng thêm</th><th>Trạng thái</th></tr></thead><tbody>${data.packages.map(p=>`<tr><td>${esc(p.code)}</td><td><input data-amount="${esc(p.code)}" type="number" value="${p.amount_vnd}"></td><td><input data-reward="${esc(p.code)}" type="number" value="${p.reward_amount}"> ${esc(p.reward_asset_code)}</td><td><input data-bonus="${esc(p.code)}" type="number" value="${p.bonus_amount}"></td><td><input data-active="${esc(p.code)}" type="checkbox" ${p.active?'checked':''}></td></tr>`).join('')}</tbody></table></div><button class="btn btn-primary" id="saveTopupPackages">Lưu gói nạp</button></div>
  <div class="card"><h3>Đơn gần nhất</h3><div class="table-wrap"><table><thead><tr><th>Mã đơn</th><th>Discord</th><th>VND</th><th>Thưởng</th><th>Trạng thái</th><th>Tạo lúc</th><th>Thanh toán</th></tr></thead><tbody>${data.orders.map(o=>`<tr><td>${o.order_code}</td><td>${o.discord_user_id}</td><td>${fmt(o.amount_vnd)}</td><td>${fmt(o.reward_amount)} ${esc(o.reward_asset_code)}</td><td>${esc(o.status)}</td><td>${esc(o.created_at||'')}</td><td>${esc(o.paid_at||'—')}</td></tr>`).join('')}</tbody></table></div></div>`;
  $('#topupUi').onsubmit=async e=>{e.preventDefault();const h=writeHeaders(true);if(!h)return;await api('/api/topup/ui',{method:'POST',headers:h,body:JSON.stringify({title:$('#topupTitle').value,instructions:$('#topupInstructions').value,footer:$('#topupFooter').value,version:data.ui.version})});showNotice('Đã lưu giao diện !nap.','warning');await renderTopup();};
  $('#saveTopupPackages').onclick=async()=>{const h=writeHeaders(true);if(!h)return;const packages=data.packages.map(p=>({code:p.code,amount_vnd:Number($(`[data-amount="${p.code}"]`).value),reward_amount:Number($(`[data-reward="${p.code}"]`).value),bonus_amount:Number($(`[data-bonus="${p.code}"]`).value),active:$(`[data-active="${p.code}"]`).checked,version:p.version}));await api('/api/topup/packages',{method:'POST',headers:h,body:JSON.stringify({packages})});showNotice('Đã lưu gói nạp.','warning');await renderTopup();};
}
function cultivationRarityColor(rarity){return {COMMON:'#95a5a6',UNCOMMON:'#2ecc71',RARE:'#3498db',EPIC:'#9b59b6',LEGENDARY:'#f1c40f',MYTHIC:'#e74c3c',ANCIENT:'#e67e22',DIVINE:'#00d2d3',RELIC:'#ff6b81',GOD:'#ffffff'}[rarity]||'#5b8cff';}
function cultivationBotPreview(ui){
  return `<section class="card"><h2>Xem trước đúng giao diện !tl</h2><div id="cuPreviewCard" style="border-left:4px solid ${cultivationRarityColor(ui.color_rarity)};padding:16px;background:#101925;border-radius:8px"><img id="cuPreviewImage" src="${esc(ui.thumbnail_url||'')}" alt="Ảnh Tu luyện" style="${ui.thumbnail_url?'':'display:none;'}float:right;width:92px;height:92px;object-fit:cover;border-radius:8px;margin-left:12px"><h3 id="cuPreviewTitle">${esc(ui.title||'TU LUYỆN')}</h3><p id="cuPreviewDescription">${esc(ui.description||'')}</p><hr><b>Cảnh giới & Tu vi</b><p>Phàm Nhân · Tầng 3 / 10<br><b>372 / 650</b> · 57.2%<br>▰▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱<br>Còn <b>278 Tu vi</b></p><b>Tu luyện</b><p>Tự động <b>+5 Tu vi / 5 giây</b><br>Voice: <b>Đang vận chuyển linh khí mỗi 5 giây</b> · 2 người<br>Tốc độ <b>60/phút</b> · phí <b>50 Vàng/phút</b></p><div class="grid"><p><b>Đạo cụ</b><br>Đan ×35 · Trợ kiếp ×2 · Bảo hộ ×1</p><p><b>Mục tiêu kế tiếp</b><br>Phàm Nhân · Tầng 4</p></div><small id="cuPreviewFooter"><i>${esc(ui.footer||'')}</i></small></div><p>Bot dùng trực tiếp Tiêu đề, Mô tả, Màu, Ảnh và Chân trang ở biểu mẫu.</p></section>`;
}
async function renderGachaCultivation(){
  setPageMeta('Gacha & Tu luyện','GAMEPLAY / LIVE BALANCE');pageEl.innerHTML='<div class="loading">Đang tải cấu hình…</div>';
  try{
    const [rates,ui]=await Promise.all([api('/api/gameplay/trait-rates'),api('/api/gameplay/cultivation-ui')]);
    const groups=rates.items.reduce((out,row)=>{(out[row.kind]??=[]).push(row);return out;},{});
    pageEl.innerHTML=`<div class="toolbar"><button class="btn" id="traitDetails">Chỉnh tên, buff, ảnh từng kết quả</button><button class="btn" id="cultivationRules">Chỉnh tốc độ và thưởng tu luyện</button><button class="btn" id="cultivationStages">Chỉnh EXP từng tầng</button></div><div class="grid">${cultivationBotPreview(ui)}${Object.entries(groups).map(([kind,items])=>`<section class="card"><h2>${esc({RACE:'Chủng tộc',SYSTEM:'Hệ',ATTRIBUTE:'Thuộc tính',AWAKENING:'Thức tỉnh'}[kind]||kind)}</h2><p>Rate runtime; tổng phải đúng 100%.</p><div class="table-wrap"><table><thead><tr><th>Kết quả</th><th>Phẩm</th><th>Rate</th></tr></thead><tbody>${items.map(item=>`<tr><td>${esc(item.display_name)}<br><small>${esc(item.code)}</small></td><td>${esc(item.rarity)}</td><td><input type="number" min="0" max="100" step="0.0001" data-trait-kind="${esc(kind)}" data-trait-code="${esc(item.code)}" value="${esc(item.rate_percent)}"> %</td></tr>`).join('')}</tbody></table></div><p data-trait-total="${esc(kind)}"></p><button class="btn btn-primary" data-save-trait="${esc(kind)}">Lưu rate ${esc(kind)}</button></section>`).join('')}<section class="card"><h2>Giao diện Tu luyện</h2><label class="field">Tiêu đề<input id="cuTitle" value="${esc(ui.title||'')}"></label><label class="field">Mô tả<textarea id="cuDescription">${esc(ui.description||'')}</textarea></label><label class="field">Màu phẩm<select id="cuColor">${RARITY_ORDER.map(x=>`<option ${x===ui.color_rarity?'selected':''}>${x}</option>`).join('')}</select></label><label class="field">URL ảnh<input id="cuImage" value="${esc(ui.thumbnail_url||'')}"></label><label class="field">Chân trang<input id="cuFooter" value="${esc(ui.footer||'')}"></label><button class="btn btn-primary" id="saveCultivationUi">Lưu giao diện</button></section></div>`;
    const updateTotal=kind=>{const values=$$(`[data-trait-kind="${kind}"]`).map(x=>Number(x.value)||0);$(`[data-trait-total="${kind}"]`).textContent=`Tổng: ${values.reduce((a,b)=>a+b,0).toFixed(4)}% / 100%`;};
    Object.keys(groups).forEach(kind=>{$$(`[data-trait-kind="${kind}"]`).forEach(x=>x.oninput=()=>updateTotal(kind));updateTotal(kind);});
    $$('[data-save-trait]').forEach(button=>button.onclick=async()=>{const kind=button.dataset.saveTrait,items=$$(`[data-trait-kind="${kind}"]`).map(x=>({kind,code:x.dataset.traitCode,rate_percent:Number(x.value)}));const total=items.reduce((s,x)=>s+x.rate_percent,0);if(Math.abs(total-100)>0.01){alert(`Tổng ${kind} phải đúng 100%.`);return;}const headers=writeHeaders(true);if(!headers)return;await api('/api/gameplay/trait-rates',{method:'PUT',headers,body:JSON.stringify({items})});showNotice(`Đã lưu rate ${kind}. Bot dùng ngay cho lượt mới.`,'warning');});
    const refreshCultivationPreview=()=>{$('#cuPreviewCard').style.borderLeftColor=cultivationRarityColor($('#cuColor').value);$('#cuPreviewTitle').textContent=$('#cuTitle').value||'TU LUYỆN';$('#cuPreviewDescription').textContent=$('#cuDescription').value;$('#cuPreviewFooter').textContent=$('#cuFooter').value;const image=$('#cuPreviewImage'),url=$('#cuImage').value.trim();image.src=url;image.style.display=url?'block':'none';};
    ['#cuTitle','#cuDescription','#cuColor','#cuImage','#cuFooter'].forEach(id=>$(id).oninput=refreshCultivationPreview);
    $('#saveCultivationUi').onclick=async()=>{const headers=writeHeaders(true);if(!headers)return;await api('/api/gameplay/cultivation-ui',{method:'PUT',headers,body:JSON.stringify({title:$('#cuTitle').value,description:$('#cuDescription').value,color_rarity:$('#cuColor').value,thumbnail_url:$('#cuImage').value,footer:$('#cuFooter').value})});showNotice('Đã lưu giao diện tu luyện. Bot dùng đúng bố cục xem trước.','warning');};
    const open=resource=>{app.pendingCrudResource=resource;location.hash='#crud';};$('#traitDetails').onclick=()=>open('trait-wheel-defs');$('#cultivationRules').onclick=()=>open('cultivation-activity');$('#cultivationStages').onclick=()=>open('cultivation-stages');
  }catch(error){pageEl.innerHTML=`<section class="card error">Không tải được cấu hình: ${esc(error.message)}</section>`;}
}

const TITLE_BONUS_FIELDS=[['martial_power','Võ lực'],['mystic_power','Pháp lực'],['armor','Giáp'],['ward','Kháng phép'],['crit_rating','Chí mạng'],['crit_resist','Kháng chí mạng'],['penetration','Xuyên giáp'],['break_rating','Phá giáp'],['status_potency','Hiệu lực trạng thái'],['status_resist','Kháng trạng thái'],['speed','Tốc độ']];
const LOCAL_TITLE_ARTWORK={REALM_01_PHAM_THE:'phamthe_1.png',REALM_02_KHAI_NGUYEN:'khainguyen_2.png',REALM_03_LINH_HAI:'linhhai_3.png',REALM_04_TINH_QUAN:'tinhquan_4.png',REALM_05_HON_AN:'honan_5.png',REALM_06_DAO_VUC:'daovuc_6.png',REALM_07_VUC_CHU:'vucchu_7.png',REALM_08_THIEN_LUAT:'thienluat_8.png',REALM_09_THAN_CHU:'thanchu_9.png',REALM_10_CHI_THAN:'chithan_10.png',GIFT_HUNTER:'trungthu.png'};
const titleArtworkUrl=t=>t.artwork_url||(LOCAL_TITLE_ARTWORK[t.code]?`/static/title-artwork/${LOCAL_TITLE_ARTWORK[t.code]}`:'');
async function renderTitles(){
  await ensureCore();setPageMeta('Danh hiệu & Buff','ADMIN / TITLE STUDIO');hideNotice();
  let data,schema;
  try{[data,schema]=await Promise.all([api('/api/crud/title-defs?limit=1000'),api('/api/crud/title-defs/schema')]);}
  catch(e){pageEl.innerHTML=`<section class="card card-pad"><h2>Chưa sẵn sàng</h2><p>${esc(e.message)}</p><p class="muted">Cần migration V97 để quản lý buff chỉ số.</p></section>`;return;}
  if(!schema.columns?.some(c=>c.column_name==='stat_bonuses')||!schema.columns?.some(c=>c.column_name==='artwork_asset_key')){pageEl.innerHTML='<section class="card card-pad"><h2>Đang chờ schema V97</h2><p class="muted">Bot cần áp dụng migration V97 trước khi Admin bật trang Danh hiệu & Buff.</p></section>';return;}
  const rows=data.rows||[];
  pageEl.innerHTML=`<section class="card card-pad domain-hero"><div><div class="eyebrow">DANH HIỆU · ${rows.length} MỤC</div><h2>Danh hiệu & Buff</h2><p class="muted">Quản lý tên, nguồn mở khóa, ảnh và buff thật của nhân vật. Emoji title cũ đã ẩn khỏi form; logo Cảnh giới giữ riêng.</p></div><button id="titleNew" class="btn btn-primary">＋ Thêm danh hiệu</button></section><div class="toolbar"><div class="search"><input id="titleSearch" placeholder="Tìm mã hoặc tên danh hiệu…"></div><select id="titleSource"><option value="">Mọi nguồn</option><option>REALM</option><option>GIFTCODE</option><option>ADMIN</option></select></div><div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Danh hiệu</th><th>Nguồn</th><th>Buff</th><th>Trạng thái</th><th></th></tr></thead><tbody id="titleRows"></tbody></table></div></div>`;
  const summary=t=>{const parts=[];if(t.vitality_flat)parts.push(`+${fmt(t.vitality_flat)} Máu`);if(t.attack_flat)parts.push(`+${fmt(t.attack_flat)} Công`);if(t.monster_cooldown_reduction_percent)parts.push(`-${t.monster_cooldown_reduction_percent}% CD quái`);for(const [key,label] of TITLE_BONUS_FIELDS)if(t.stat_bonuses?.[key])parts.push(`+${fmt(t.stat_bonuses[key])} ${label}`);return parts.join(' · ')||'Không có buff';};
  const paint=()=>{const q=$('#titleSearch').value.trim().toLowerCase(),source=$('#titleSource').value;const list=rows.filter(t=>(!q||`${t.code} ${t.display_name_vi}`.toLowerCase().includes(q))&&(!source||t.source_type===source));$('#titleRows').innerHTML=list.map(t=>`<tr><td>${titleArtworkUrl(t)?`<img src="${esc(titleArtworkUrl(t))}" alt="" style="max-width:130px;max-height:36px;display:block;margin-bottom:5px">`:''}<b>${esc(t.display_name_vi)}</b><div class="muted tiny code">${esc(t.code)}</div></td><td>${esc(t.source_type)}${t.realm_ordinal?` · Bậc ${t.realm_ordinal}`:''}</td><td>${esc(summary(t))}</td><td>${statusBadge(t.active)}</td><td><button class="btn btn-secondary btn-small" data-title-edit="${esc(t.code)}">Sửa</button></td></tr>`).join('')||'<tr><td colspan="5"><div class="empty">Không có danh hiệu.</div></td></tr>';$$('[data-title-edit]').forEach(button=>button.onclick=()=>openTitle(rows.find(t=>t.code===button.dataset.titleEdit)));};
  $('#titleSearch').oninput=paint;$('#titleSource').onchange=paint;$('#titleNew').onclick=()=>openTitle(null);paint();
}
function openTitle(title){
  const creating=!title,bonus=title?.stat_bonuses||{};
  const numeric=(id,label,value,max='1000000000')=>`<div class="field"><label>${label}</label><input id="${id}" type="number" min="0" max="${max}" step="1" value="${esc(value??0)}"></div>`;
  openDrawer(creating?'Thêm danh hiệu':title.display_name_vi,'TITLE STUDIO / BUFF',`<div class="grid grid-2"><div class="field span-2"><label>Mã danh hiệu</label><input id="titleCode" value="${esc(title?.code||'')}" ${creating?'':'disabled'} placeholder="EVENT_CHAMPION"></div><div class="field span-2"><label>Tên hiển thị</label><input id="titleName" value="${esc(title?.display_name_vi||'')}"></div><div class="field"><label>Nguồn mở khóa</label><select id="titleType">${['REALM','GIFTCODE','ADMIN'].map(s=>`<option value="${s}" ${title?.source_type===s?'selected':''}>${s}</option>`).join('')}</select></div><div class="field"><label>Bậc cảnh giới (chỉ REALM)</label><select id="titleRealm"><option value="">Không dùng</option>${Array.from({length:10},(_,i)=>`<option value="${i+1}" ${title?.realm_ordinal===i+1?'selected':''}>Bậc ${i+1}</option>`).join('')}</select></div><div class="field span-2"><label>Mô tả</label><textarea id="titleDescription">${esc(title?.description||'')}</textarea></div><div class="field span-2"><label class="check-row"><input id="titleActive" type="checkbox" ${title?.active===false?'':'checked'}> Đang hoạt động</label></div>${numeric('titleVitality','Máu cộng thêm',title?.vitality_flat)}${numeric('titleAttack','Công cộng thêm',title?.attack_flat)}${numeric('titleCooldown','Giảm hồi chiêu đánh quái (%)',title?.monster_cooldown_reduction_percent,90)}<div class="field span-2"><h3>Buff chỉ số chiến đấu</h3><p class="muted">Chỉ số cộng thẳng vào nhân vật khi mang danh hiệu.</p></div>${TITLE_BONUS_FIELDS.map(([key,label])=>numeric(`titleStat_${key}`,label,bonus[key])).join('')}</div><div class="drawer-actions"><button id="titleSave" class="btn btn-primary">${creating?'Tạo danh hiệu':'Lưu thay đổi'}</button></div>${creating?'':`<div class="field"><label>Cấp danh hiệu cho Player ID (UUID)</label><div class="inline-fields"><input id="titleGrantPlayer" placeholder="Player UUID"><button id="titleGrant" class="btn btn-secondary">Cấp</button></div></div>`}<p class="muted">Artwork danh hiệu quản lý riêng bằng ảnh. Emoji cũ không cần nhập ở đây.</p>`);
  if(!creating){
    $('#titleActive').closest('.field').insertAdjacentHTML('afterend',`<div class="field span-2"><label>Artwork danh hiệu</label>${titleArtworkUrl(title)?`<img src="${esc(titleArtworkUrl(title))}" alt="${esc(title.display_name_vi)}" style="max-width:100%;max-height:100px;display:block;margin:8px 0">`:'<p class="muted">Chưa có ảnh trong kho media.</p>'}<input id="titleArtworkFile" type="file" accept="image/png,image/jpeg,image/webp"><button id="titleArtworkUpload" class="btn btn-secondary" style="margin-top:8px">Tải ảnh lên</button></div>`);
    $('#titleArtworkUpload').onclick=async()=>{const file=$('#titleArtworkFile').files[0];if(!file){alert('Chọn ảnh trước.');return;}const headers=writeHeaders(false);if(!headers)return;const body=new FormData();body.append('file',file);try{await api(`/api/content-media/title/${encodeURIComponent(title.code)}/image`,{method:'POST',headers,body});closeDrawer();showNotice('Đã cập nhật ảnh danh hiệu trong kho media.','warning');await renderTitles();}catch(e){alert(e.message);}};
  }
  const syncRealm=()=>{$('#titleRealm').disabled=$('#titleType').value!=='REALM';if($('#titleRealm').disabled)$('#titleRealm').value='';};$('#titleType').onchange=syncRealm;syncRealm();
  $('#titleSave').onclick=async()=>{const integer=(selector,max=1e9)=>{const n=Number($(selector).value);if(!Number.isSafeInteger(n)||n<0||n>max)throw Error('Buff phải là số nguyên không âm trong giới hạn.');return n;};try{const stats={};for(const [key] of TITLE_BONUS_FIELDS){const value=integer(`#titleStat_${key}`);if(value)stats[key]=value;}const payload={display_name_vi:$('#titleName').value.trim(),source_type:$('#titleType').value,realm_ordinal:$('#titleRealm').value?Number($('#titleRealm').value):null,description:$('#titleDescription').value.trim(),active:$('#titleActive').checked,vitality_flat:integer('#titleVitality'),attack_flat:integer('#titleAttack'),monster_cooldown_reduction_percent:integer('#titleCooldown',90),stat_bonuses:stats};if(creating)payload.code=$('#titleCode').value.trim().toUpperCase();const headers=writeHeaders(true);if(!headers)return;const path=creating?'/api/crud/title-defs':`/api/crud/title-defs?pk=${encodeURIComponent(JSON.stringify({code:title.code}))}`;await api(path,{method:creating?'POST':'PATCH',headers,body:JSON.stringify(payload)});closeDrawer();showNotice(creating?'Đã tạo danh hiệu.':'Đã lưu danh hiệu và buff.','warning');await renderTitles();}catch(e){alert(e.message);}};
  if(!creating)$('#titleGrant').onclick=async()=>{const headers=writeHeaders(true);if(!headers)return;try{await api(`/api/titles/${encodeURIComponent(title.code)}/grant`,{method:'POST',headers,body:JSON.stringify({player_id:$('#titleGrantPlayer').value.trim()})});showNotice('Đã cấp danh hiệu cho người chơi.','warning');closeDrawer();}catch(e){alert(e.message);}};
}

const routes = {topup:renderTopup,shop:renderSystemShop,command:renderCommandCenter,dashboard:renderDashboard,players:renderPlayers,discordprofile:renderDiscordProfile,items:renderItems,materials:renderMaterials,media:renderMedia,characters:renderCharacters,gachacultivation:renderGachaCultivation,contentmedia:renderContentMedia,sets:renderSets,testmedia:renderTestMedia,giftcodes:renderGiftcodes,titles:renderTitles,character:()=>renderDomainHub('character'),world:()=>renderDomainHub('world'),progression:()=>renderDomainHub('progression'),social:()=>renderDomainHub('social'),economy:()=>renderDomainHub('economy'),crud:()=>{const r=app.pendingCrudResource;app.pendingCrudResource=null;return renderCrudStudio(r);},runtime:renderRuntimeState,content:renderContent,liveops:()=>renderDomainHub('liveops'),discordops:renderDiscordOps,ops:renderOps,quality:renderDataQuality,bulk:renderBulkTools,database:renderDatabase,staged:renderStaged};
async function navigate() {
  closeDrawer();
  const route=(location.hash||'#command').slice(1);
  app.route=routes[route]?route:'command'; setActiveNav(app.route);
  pageEl.innerHTML='<div class="card empty">Đang tải…</div>';
  try { await routes[app.route](); }
  catch(e){ console.error(e); pageEl.innerHTML=`<div class="card empty">Không tải được trang: ${esc(e.message)}</div>`; showNotice(e.message,'error'); }
}
window.addEventListener('hashchange',navigate);
$('#refreshBtn').onclick=async()=>{app.dashboard=null;app.commandCenter=null;app.quality=null;app.players=null;app.items=null;app.sets=null;app.schemas=null;app.crudResources=null;app.runtimeGroups=null;app.crudSchemaCache.clear();app.tableCache.clear();await navigate();};
$('#exportBtn').onclick=()=>{if(Object.keys(getStaged()).length){downloadText('lost_kingsland_admin_staged_changes.sql',allStagedSql());}else{location.hash='#staged';}};

// Global command search across items / players / sets.
const globalSearchInput=$('#globalSearch'), globalSearchResults=$('#globalSearchResults');
let globalSearchTimer=null;
if(globalSearchInput){
  globalSearchInput.oninput=()=>{
    clearTimeout(globalSearchTimer);
    const q=globalSearchInput.value.trim();
    if(q.length<2){globalSearchResults.classList.add('hidden');globalSearchResults.innerHTML='';return;}
    globalSearchTimer=setTimeout(async()=>{
      try{
        const r=await api(`/api/global-search?q=${encodeURIComponent(q)}&limit=40`);
        globalSearchResults.innerHTML=(r.results||[]).map(x=>`<button class="global-result" data-type="${esc(x.type)}" data-id="${esc(x.id)}" data-route="${esc(x.route)}">${x.image_url?`<img src="${esc(x.image_url)}" alt="">`:'<span class="global-result-icon">⌕</span>'}<span><b>${esc(x.title)}</b><small>${esc(x.subtitle||'')}</small></span><em>${esc(x.type)}</em></button>`).join('')||'<div class="global-empty">Không tìm thấy.</div>';
        globalSearchResults.classList.remove('hidden');
        $$('.global-result',globalSearchResults).forEach(b=>b.onclick=()=>{
          const type=b.dataset.type,id=b.dataset.id,route=b.dataset.route;
          globalSearchResults.classList.add('hidden');globalSearchInput.value='';location.hash='#'+route;
          setTimeout(()=>{if(type==='ITEM'&&app.items)openItem(id);if(type==='PLAYER'&&app.players)openPlayer(id);},650);
        });
      }catch(e){globalSearchResults.innerHTML=`<div class="global-empty">${esc(e.message)}</div>`;globalSearchResults.classList.remove('hidden');}
    },250);
  };
  document.addEventListener('click',e=>{if(!e.target.closest('.global-search'))globalSearchResults.classList.add('hidden');});
}

updateStagedCount();
applyAdvancedMode();

(async function boot(){
  try { app.meta=await api('/api/meta'); updateMode(); await navigate(); }
  catch(e){ modePill.textContent='Không kết nối được Admin API'; pageEl.innerHTML=`<div class="card empty">${esc(e.message)}</div>`; }
})();
