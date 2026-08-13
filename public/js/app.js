// app.html(로그인 후 대시보드) 전용 로직. common.js가 먼저 로드되어 있어야 함.
// 이 앱은 챗봇 하나로 운영된다: 공문판별/승인번호조회/업체확인/합격표시번호조회·등록/알림확인/
// 내소화기함조회 같은 모든 기능은 채팅 메시지로 실행되고(chat_tools.py가 감지해 실제 로직을 호출),
// 화면에는 그 기능을 어떻게 쓰는지 안내하는 "프리셋 카드"만 둔다. 관제 대시보드만 관리자 전용
// 별도 탭으로 남는다.
if (!requireAuthOrRedirect()) {
  // 리다이렉트 처리 중 - 이후 코드 실행 방지
  throw new Error("__redirect_to_login__");
}

(function initWhoami(){
  const u = currentUser();
  document.getElementById("whoami").textContent = u ? `👤 ${u.email}${u.role === "admin" ? " (관리자)" : ""}` : "";
})();

/* ===================== 권한(관리자) ===================== */
function isAdmin(){ const u = currentUser(); return !!u && u.role === "admin"; }
(function applyRoleVisibility(){
  const admin = isAdmin();
  const navAdmin = document.getElementById("navAdmin");
  if (navAdmin) navAdmin.style.display = admin ? "flex" : "none";
})();

/* ===================== 서버 상태 ===================== */
async function loadHealth(){
  try {
    const r = await fetch("/api/health"); const body = await r.json();
    document.getElementById("noticeBox").innerHTML =
      `⚠ 현재 <b>${body.mockMode ? "MOCK 모드" : "실 KFI API 모드"}</b>로 동작 중입니다. ` +
      (body.mockMode ? "실 데이터로 전환하려면 .env에 KFI_SERVICE_KEY를 설정하고 USE_MOCK=false로 바꾸세요(README 참고)." : "실제 data.go.kr 응답을 사용합니다.");
  } catch {
    document.getElementById("noticeBox").innerHTML = "🚨 백엔드 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.";
  }
}
loadHealth();

/* ===================== 사이드바 탭 전환 ===================== */
const VIEW_TITLES = {
  chat: "챗봇 상담",
  admin: "통합 관제 대시보드",
};
function switchView(viewName){
  if (viewName === "admin" && !isAdmin()){
    alert("관제 대시보드는 관리자만 접근할 수 있습니다.");
    return;
  }
  document.querySelectorAll(".view").forEach(el => el.classList.remove("active"));
  document.getElementById("view-" + viewName).classList.add("active");
  document.querySelectorAll(".navitem").forEach(el => el.classList.toggle("active", el.dataset.view === viewName));
  document.getElementById("pageTitle").innerHTML = `<span class="badge">2026 KFI AI 혁신 경진대회</span>${VIEW_TITLES[viewName] || ""}`;
  if (viewName === "admin") loadAdminDashboard();
}

/* ===================== 알림 배지(사이드바) ===================== */
async function loadNotifCount(){
  const r = await fetch("/api/notifications/mine", { headers: authHeaders() });
  if (!r.ok) return;
  const list = await r.json();
  const el = document.getElementById("notifCount");
  if (list.length){ el.style.display = "inline-block"; el.textContent = list.length; }
  else el.style.display = "none";
}
loadNotifCount();

/* ===================== 리콜 시뮬레이션(관리자) ===================== */
async function simulateRecallEvent(){
  const number = "성능인증 제2023-7-118호";
  const r = await fetch("/api/admin/simulate-recall", { method:"POST", headers:{"Content-Type":"application/json", ...authHeaders()}, body: JSON.stringify({ number }) });
  const body = await r.json();
  const banner = document.getElementById("recallAlert");
  if (!r.ok){ banner.className="alert-banner show"; banner.textContent = "⚠ " + (body.detail || body.error || "리콜 시뮬레이션 실패"); return; }
  banner.className="alert-banner show";
  banner.textContent = `🔔 리콜 발생: "${number}"이(가) 취소되었습니다. 영향받은 사용자 ${body.notified}명에게 알림이 발송(DB 기록)되었습니다.`;
  loadNotifCount();
}

/* ===================== 관제 대시보드 ===================== */
async function loadAdminDashboard(){
  if (!isAdmin()) return;
  const statsR = await fetch("/api/reports/stats", { headers: authHeaders() }); const stats = await statsR.json();
  document.getElementById("statFraud").textContent = stats.fraud;
  document.getElementById("statMaint").textContent = stats.maintenance;
  const max = Math.max(...stats.byRegion.map(r=>r.c), 1);
  document.getElementById("regionBars").innerHTML = stats.byRegion.length
    ? stats.byRegion.map(r=>{ const pct=Math.round((r.c/max)*100); return `<div class="bar-row"><div class="name">${r.region}</div><div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div><div class="val">${r.c}</div></div>`; }).join("")
    : '<div style="color:#999;font-size:13px;">아직 접수 내역이 없습니다.</div>';

  const listR = await fetch("/api/reports", { headers: authHeaders() }); const list = await listR.json();
  const body = document.getElementById("reportTableBody");
  body.innerHTML = list.length ? list.map(r=>{
    const cls = r.risk_level==="위험"?"danger":r.risk_level==="주의"?"warn":"safe";
    return `<tr><td>${r.created_at}</td><td><span class="badge-type">${r.type==="fraud"?"사기신고":"점검요청"}</span></td><td>${r.region}</td><td>${escapeHtml(r.target)}</td><td>${escapeHtml(r.reason)}</td><td><span class="badge-lv ${cls}">${r.risk_level}</span></td></tr>`;
  }).join("") : `<tr class="empty-row"><td colspan="6">아직 접수된 내역이 없습니다.</td></tr>`;
}

/* ===================== 챗봇: 프리셋 카드 ===================== */
// 클릭하면 실제로 실행되는 게 아니라, 채팅 입력창에 빈칸을 채우면 되는 완성형 문구를 넣어준다.
// {{...}} 로 감싼 부분이 "빈칸"이며, 입력창에 넣을 때는 괄호를 벗기고 그 자리를 선택 상태로 만들어
// 사용자가 바로 타이핑해서 채울 수 있게 한다.
// photo:true 인 항목은 문장 입력 대신(또는 대신해서) 📷 아이콘으로 사진을 업로드해도 되는 기능이다.
const PRESETS = [
  { icon:"🧾", label:"공문 판별", template:"{{여기에 공문·안내문 내용을 붙여넣으세요}}", photo:true },
  { icon:"📋", label:"승인번호 조회", template:"{{형식승인 제0000-0-000호}} 진짜예요?" },
  { icon:"🏢", label:"업체 확인", template:"{{업체명}} 등록된 업체 맞나요?" },
  { icon:"📦", label:"소화기 조회·등록", template:"{{합격표시번호}} 조회해줘", photo:true },
  { icon:"🗄", label:"내 소화기함 보기", template:"내 소화기함 보여줘" },
  { icon:"🔔", label:"내 알림 확인", template:"내 알림 확인" },
];
function renderPresets(){
  const box = document.getElementById("presetGrid");
  box.innerHTML = PRESETS.map((p,i)=>`<div class="preset-card" onclick="usePreset(${i})" ${p.photo ? 'title="문장 입력 대신 📷 버튼으로 사진을 업로드해도 돼요"' : ""}><div class="ic">${p.icon}</div><div class="lab">${p.label}</div>${p.photo ? '<span class="photo-badge" title="사진 업로드 가능">📷</span>' : ""}</div>`).join("");
}
function usePreset(i){
  const p = PRESETS[i];
  const input = document.getElementById("chatInput");
  const m = p.template.match(/\{\{(.+?)\}\}/);
  if (m){
    input.value = p.template.replace(/\{\{(.+?)\}\}/, m[1]);
    input.focus();
    const start = p.template.indexOf(m[0]);
    input.setSelectionRange(start, start + m[1].length);
  } else {
    input.value = p.template;
    input.focus();
  }
}
renderPresets();

/* ===================== 챗봇: OCR(사진으로 확인) ===================== */
async function runChatOCR(input){
  const f = input.files[0]; if (!f) return;
  const status = document.getElementById("chatOcrStatus");
  status.textContent = "⏳ 이미지를 인식하는 중입니다...";
  try {
    const { data:{ text } } = await Tesseract.recognize(f, "kor+eng", {
      logger:(m)=>{ if (m.status && m.progress!=null) status.textContent = `⏳ ${m.status} (${Math.round(m.progress*100)}%)`; }
    });
    status.textContent = text.trim() ? "✅ 인식 완료 — 필요하면 수정 후 전송하세요." : "⚠ 텍스트를 인식하지 못했습니다. 직접 입력해주세요.";
    if (text.trim()){ document.getElementById("chatInput").value = text.trim(); document.getElementById("chatInput").focus(); }
  } catch(err){
    status.textContent = "⚠ OCR 인식 실패. 직접 입력해주세요. (" + err.message + ")";
  }
  input.value = "";
}

/* ===================== 챗봇: 대화 ===================== */
function askQuick(q){ document.getElementById("chatInput").value = q; sendChat(); }

function appendChatMsg(role, html){
  const body = document.getElementById("chatBody");
  const div = document.createElement("div");
  div.className = "chat-msg " + (role === "user" ? "user" : "bot");
  div.innerHTML = html;
  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
}

/* 채팅 결과가 "위험/미등록/리콜" 등으로 나오면, 그 자리에서 바로 신고할 수 있는 버튼을 붙인다. */
const reportRegistry = [];
function buildReportInfoForTool(tool, args, result){
  if (tool === "check_approval" && (result.status === "unregistered" || result.status === "cancelled")){
    return { type:"fraud", target: (args && args.number) || "", reason: result.status === "cancelled" ? "취소(리콜)됨" : "미등록", riskLevel:"위험", buttonLabel:"이 승인번호 신고하기" };
  }
  if (tool === "check_company" && result.status === "unregistered"){
    return { type:"fraud", target: (args && args.name) || "", reason:"미등록 업체", riskLevel:"위험", buttonLabel:"이 업체 신고하기" };
  }
  if (tool === "analyze_doc" && result.level && result.level !== "저위험"){
    return { type:"fraud", target:"공문/안내문", reason: result.level, riskLevel: result.level === "고위험" ? "위험" : "주의", buttonLabel:"이 공문 신고하기" };
  }
  if (tool === "check_unit" && result.found && result.grade && result.grade !== "안전"){
    return { type:"maintenance", target: result.unit.code, reason: result.recall ? "리콜 이력" : result.ageStatus, riskLevel: result.grade, buttonLabel:"점검·교체 요청" };
  }
  return null;
}
function buildReportRow(info){
  const idx = reportRegistry.push(info) - 1;
  return `<div class="chat-report-row">
    <select id="chatReportRegion_${idx}"><option>서울특별시</option><option>경기도</option><option>인천광역시</option><option>부산광역시</option><option>기타 지역</option></select>
    <button class="btn-report" id="chatReportBtn_${idx}" onclick="submitChatReport(${idx})">🚨 ${info.buttonLabel}</button>
  </div>`;
}
async function submitChatReport(idx){
  const info = reportRegistry[idx];
  if (!info) return;
  const region = document.getElementById("chatReportRegion_" + idx).value;
  const r = await fetch("/api/reports", { method:"POST", headers:{"Content-Type":"application/json", ...authHeaders()}, body: JSON.stringify({ type:info.type, region, target:info.target, reason:info.reason, riskLevel:info.riskLevel }) });
  const btn = document.getElementById("chatReportBtn_" + idx);
  if (r.ok){ alert("접수되었습니다. (서버에 저장됨)"); if (btn){ btn.disabled = true; btn.textContent = "✅ 접수됨"; } }
  else alert("접수 실패");
}

async function sendChat(){
  const input = document.getElementById("chatInput");
  const message = input.value.trim();
  if (!message) return;
  appendChatMsg("user", escapeHtml(message));
  input.value = "";

  appendChatMsg("bot", '<span style="color:#999">답변 생성 중...</span>');
  const body = document.getElementById("chatBody");
  const loadingEl = body.lastChild;

  try {
    const r = await fetch("/api/chat", { method:"POST", headers:{"Content-Type":"application/json", ...authHeaders()}, body: JSON.stringify({ message }) });
    const data = await r.json();
    body.removeChild(loadingEl);

    if (!r.ok){ appendChatMsg("bot", "⚠ 오류: " + escapeHtml(data.error || "알 수 없는 오류")); return; }

    if (data.mode === "tool"){
      let html = `<div class="src" style="margin:0 0 4px;">🔎 채팅으로 바로 조회함</div>`;
      html += escapeHtml(data.answer).replace(/\n/g, "<br>");
      const info = buildReportInfoForTool(data.tool, data.args, data.result);
      if (info) html += buildReportRow(info);
      appendChatMsg("bot", html);
      if (data.tool === "list_notifications") loadNotifCount();
    } else if (data.mode === "llm"){
      let html = escapeHtml(data.answer).replace(/\n/g, "<br>");
      if (data.sources && data.sources.length) html += `<div class="src">참고: ${data.sources.map(s=>escapeHtml(s.title)).join(", ")}</div>`;
      appendChatMsg("bot", html);
    } else {
      let html = `<div>${escapeHtml(data.note || "관련 참고자료입니다.")}</div>`;
      (data.sources || []).forEach(s => {
        html += `<div class="src-card"><b>${escapeHtml(s.title)}</b><br>${escapeHtml(s.text).slice(0,220)}${s.text.length>220?"...":""}</div>`;
      });
      if (!data.sources || !data.sources.length) html += `<div style="color:#999;margin-top:6px;">관련 자료를 찾지 못했습니다.</div>`;
      appendChatMsg("bot", html);
    }
  } catch (e) {
    body.removeChild(loadingEl);
    appendChatMsg("bot", "⚠ 서버와 통신할 수 없습니다.");
  }
}
