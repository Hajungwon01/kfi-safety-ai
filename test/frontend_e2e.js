// 실제 FastAPI 서버(uvicorn, 이미 실행 중이어야 함: PORT=4600)에 연결된 프론트엔드를
// jsdom으로 렌더링해 실제 fetch 통신까지 포함한 end-to-end 검증을 수행한다.
// 앱은 챗봇 하나로 운영되므로(프리셋 카드 + 채팅), 이 파일은 로그인/권한 가드/관제 대시보드
// 접근제어처럼 "화면 전환" 레벨을 검증하고, 채팅으로 실제 기능이 실행되는 상세 시나리오는
// chat_widget_e2e.js에서 다룬다.
const path = require("path");
const fs = require("fs");
const { JSDOM } = require("jsdom");

let pass = 0, fail = 0;
function assert(cond, msg) { if (cond) { pass++; console.log("  ✅", msg); } else { fail++; console.error("  ❌", msg); } }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
const ORIGIN = "http://localhost:4600";
const PUBLIC = path.join(__dirname, "..", "public");

function loadPage(fileName) {
  let html = fs.readFileSync(path.join(PUBLIC, fileName), "utf-8");
  html = html.replace(/<script src="https:\/\/cdn\.jsdelivr\.net[^>]*><\/script>/, "");
  const dom = new JSDOM(html, { runScripts: "dangerously", url: ORIGIN + "/" + fileName });
  const { window } = dom;
  window.fetch = (input, init) => {
    const url = (typeof input === "string" && input.startsWith("/")) ? ORIGIN + input : input;
    return fetch(url, init);
  };
  window.alert = () => {};
  window.HTMLElement.prototype.scrollIntoView = () => {};
  return { dom, window, doc: window.document };
}
function evalFile(window, relPath) {
  const code = fs.readFileSync(path.join(PUBLIC, relPath), "utf-8");
  window.eval(code);
}
function spyLocation(window) {
  const spy = { href: null };
  window.redirectTo = (path) => { spy.href = path; };
  return spy;
}

async function main() {
  console.log("\n[0] 로그인 페이지: 회원가입 -> 토큰 발급 + app.html 리다이렉트 시도");
  const loginPage = loadPage("login.html");
  evalFile(loginPage.window, "js/common.js");
  const loginSpy = spyLocation(loginPage.window);
  evalFile(loginPage.window, "js/login.js");
  loginPage.doc.getElementById("authEmail").value = "fe-test@example.com";
  loginPage.doc.getElementById("authPassword").value = "pw1234";
  await loginPage.window.doRegister();
  await sleep(200);
  const issuedToken = loginPage.window.localStorage.getItem("kfi_token");
  assert(!!issuedToken, "회원가입 성공 후 토큰이 localStorage에 저장됨");
  assert(loginSpy.href === "/app.html", "회원가입 성공 시 app.html로 리다이렉트 시도됨");

  console.log("\n[0-1] 토큰 없이 app.html 접근 시 로그인 페이지로 리다이렉트");
  const guardPage = loadPage("app.html");
  evalFile(guardPage.window, "js/common.js");
  const guardSpy = spyLocation(guardPage.window);
  try { evalFile(guardPage.window, "js/app.js"); } catch { /* 인증 가드가 throw로 이후 코드 실행을 막음 - 정상 동작 */ }
  assert(guardSpy.href === "/login.html", "토큰 없이 app.html 접근 시 로그인 페이지로 리다이렉트 시도됨");

  console.log("\n[1] app.html 로드(토큰 보유): 서버 상태/사용자 표시 + 기본 화면이 챗봇인지 + 프리셋 카드 렌더링");
  const appPage = loadPage("app.html");
  appPage.window.localStorage.setItem("kfi_token", issuedToken);
  evalFile(appPage.window, "js/common.js");
  evalFile(appPage.window, "js/app.js");
  const $ = (id) => appPage.doc.getElementById(id);
  const win = appPage.window;
  await sleep(300);
  assert($("noticeBox").textContent.includes("MOCK"), "헬스체크 결과가 화면에 반영됨(MOCK 모드 표시)");
  assert($("whoami").textContent.includes("fe-test@example.com"), "로그인 사용자 표시됨");
  assert(!$("whoami").textContent.includes("관리자"), "일반 회원가입 사용자는 관리자로 표시되지 않음");
  assert(win.document.getElementById("view-chat").classList.contains("active"), "로그인 직후 기본 화면은 챗봇");
  assert($("pageTitle").textContent.includes("챗봇 상담"), "상단 타이틀도 챗봇 상담으로 표시됨");
  assert($("presetGrid").querySelectorAll(".preset-card").length === 6, "프리셋 카드 6개가 렌더링됨(공문판별/승인번호/업체/소화기조회등록/소화기함/알림)");
  assert(!!$("chatImage"), "채팅창에 사진(OCR) 업로드 아이콘이 있음");

  console.log("\n[2] 프리셋 카드 클릭 -> 채팅으로 전송되지 않고 입력창에 완성형 문구만 채워짐 (바로 실행되지 않음)");
  const beforeMsgCount = $("chatBody").children.length;
  win.usePreset(1); // 승인번호 조회
  assert($("chatBody").children.length === beforeMsgCount, "프리셋 클릭은 채팅 말풍선을 추가하지 않음(자동 실행 아님)");
  assert($("chatInput").value === "형식승인 제0000-0-000호 진짜예요?", "승인번호 조회 프리셋은 입력창에 완성형 예시 문구를 채워줌");

  console.log("\n[3] 채팅으로 공문/승인번호/업체를 직접 조회 (실서버 API 통신, 챗봇이 1부 기능 직접 실행)");
  $("chatInput").value = "리튬이온 전용 소화기를 즉시 비치하지 않으면 과태료가 부과됩니다. 오늘까지 계좌로 입금 바랍니다.";
  await win.sendChat();
  await sleep(150);
  let last = $("chatBody").lastChild;
  assert(last.textContent.includes("고위험"), "문서판별 결과: 고위험 표시");
  assert(last.innerHTML.includes("이 공문 신고하기"), "고위험 공문은 채팅 버블 안에 바로 신고 버튼이 뜸");

  $("chatInput").value = "성능인증 제2023-7-118호 이거 진짜예요?";
  await win.sendChat();
  await sleep(150);
  last = $("chatBody").lastChild;
  assert(last.textContent.includes("정상 등록"), "승인번호 결과: 정상 등록 표시");
  assert(!last.innerHTML.includes("신고하기"), "정상 등록된 승인번호는 신고 버튼이 뜨지 않음");

  $("chatInput").value = "대한안전산업(주)에서 사려는데 등록된 업체 맞나요?";
  await win.sendChat();
  await sleep(150);
  last = $("chatBody").lastChild;
  assert(last.textContent.includes("등록"), "판매자 결과: 등록업체 표시");
  assert(!last.innerHTML.includes("신고하기"), "등록된 업체는 신고 버튼이 뜨지 않음");

  console.log("\n[4] 채팅으로 소화기 조회 -> 자동 등록 -> 내 소화기함/알림도 채팅으로 확인");
  $("chatInput").value = "EYTN-52981 조회해줘";
  await win.sendChat();
  await sleep(300);
  last = $("chatBody").lastChild;
  assert(last.textContent.includes("내 소화기함에 등록했습니다"), "유닛 조회 시 자동 등록 문구 표시");
  assert(last.textContent.includes("정상(내용연수 이내)"), "정상 상태의 소화기로 조회됨");

  $("chatInput").value = "내 소화기함 보여줘";
  await win.sendChat();
  await sleep(200);
  last = $("chatBody").lastChild;
  assert(last.textContent.includes("EYTN-52981"), "내 소화기함 목록에 등록된 유닛 표시(채팅으로 확인)");
  assert(last.textContent.includes("안전"), "내 소화기함 배지가 안전 상태로 표시됨");

  $("chatInput").value = "내 알림 확인";
  await win.sendChat();
  await sleep(200);
  assert($("chatBody").lastChild.textContent.includes("알림이 없습니다"), "아직 리콜 전이라 알림이 없다고 답변함");

  console.log("\n[5] 일반 사용자는 관제 대시보드에 접근할 수 없음 (프론트 가드 + 사이드바 숨김 + 백엔드 403)");
  assert($("navAdmin").style.display === "none", "일반 사용자에게는 관제 대시보드 메뉴가 보이지 않음");
  win.switchView("admin");
  assert(win.document.getElementById("view-chat").classList.contains("active"), "관리자가 아니면 관제 대시보드로 전환되지 않음(프론트 가드)");
  const forbiddenRes = await fetch(ORIGIN + "/api/admin/simulate-recall", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + issuedToken }, body: JSON.stringify({}) });
  assert(forbiddenRes.status === 403, "일반 사용자 토큰으로 리콜 시뮬레이션 API를 직접 호출해도 403 (백엔드도 실제로 막음)");
  const forbiddenStats = await fetch(ORIGIN + "/api/reports/stats", { headers: { Authorization: "Bearer " + issuedToken } });
  assert(forbiddenStats.status === 403, "일반 사용자 토큰으로 관제 통계 API를 직접 호출해도 403");

  console.log("\n[6] 관리자 로그인 -> 관제 대시보드에서 리콜 시뮬레이션 실행 (관리자 액션)");
  const adminLoginPage = loadPage("login.html");
  evalFile(adminLoginPage.window, "js/common.js");
  spyLocation(adminLoginPage.window);
  evalFile(adminLoginPage.window, "js/login.js");
  adminLoginPage.doc.getElementById("authEmail").value = "admin@kfi.go.kr";
  adminLoginPage.doc.getElementById("authPassword").value = "admin1234!";
  await adminLoginPage.window.doLogin();
  await sleep(200);
  const adminToken = adminLoginPage.window.localStorage.getItem("kfi_token");
  assert(!!adminToken, "시딩된 관리자 계정으로 로그인 성공");

  const adminPage = loadPage("app.html");
  adminPage.window.localStorage.setItem("kfi_token", adminToken);
  evalFile(adminPage.window, "js/common.js");
  evalFile(adminPage.window, "js/app.js");
  const $$ = (id) => adminPage.doc.getElementById(id);
  const adminWin = adminPage.window;
  await sleep(300);
  assert($$("whoami").textContent.includes("관리자"), "관리자 계정은 이름 옆에 (관리자) 표시가 붙음");
  assert($$("navAdmin").style.display !== "none", "관리자에게는 관제 대시보드 메뉴가 보임");
  adminWin.switchView("admin");
  assert(adminWin.document.getElementById("view-admin").classList.contains("active"), "관리자는 관제 대시보드로 정상 전환됨");
  await sleep(300);

  await adminWin.simulateRecallEvent();
  await sleep(400);
  assert($$("recallAlert").className.includes("show"), "관리자가 트리거한 리콜 배너 노출됨");
  assert($$("recallAlert").textContent.includes("영향받은 사용자 1명"), "영향받은 사용자 수 표시(1명)");
  assert(parseInt($$("statMaint").textContent) >= 0, "관제 대시보드 통계가 로딩됨 (statMaint=" + $$("statMaint").textContent + ")");
  assert(!$$("reportTableBody").textContent.includes("불러오는 중"), "최근 접수 내역 테이블이 로딩 상태를 벗어나 실데이터로 채워짐");

  console.log("\n[7] 리콜 발생 후 일반 사용자(fe-test) 쪽도 채팅으로 재조회하면 최신 상태로 반영되는지 확인");
  $("chatInput").value = "성능인증 제2023-7-118호 이거 진짜예요?";
  await win.sendChat();
  await sleep(200);
  last = $("chatBody").lastChild;
  assert(last.textContent.includes("취소"), "채팅으로 승인번호를 재조회하면 취소 상태로 반영됨");
  assert(last.innerHTML.includes("이 승인번호 신고하기"), "리콜된 승인번호는 채팅 버블 안에서 바로 신고 버튼으로 전환됨");

  $("chatInput").value = "내 소화기함 보여줘";
  await win.sendChat();
  await sleep(200);
  assert($("chatBody").lastChild.textContent.includes("위험"), "내 소화기함을 채팅으로 다시 보면 리콜 후 위험 등급으로 갱신됨");

  $("chatInput").value = "내 알림 확인";
  await win.sendChat();
  await sleep(200);
  assert($("chatBody").lastChild.textContent.includes("리콜"), "채팅으로 확인한 알림 목록에 리콜 메시지 표시");
  assert($("notifCount").textContent !== "0" && $("notifCount").style.display !== "none", "사이드바 알림 배지에 카운트 표시됨");

  console.log(`\n=== 프론트엔드 E2E 결과: ${pass}건 통과, ${fail}건 실패 ===`);
  process.exit(fail === 0 ? 0 : 1);
}

main().catch((e) => { console.error("테스트 실행 중 예외:", e); process.exit(1); });
