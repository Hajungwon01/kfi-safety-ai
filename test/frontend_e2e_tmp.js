// 실제 FastAPI 서버(uvicorn, 이미 실행 중이어야 함: PORT=4600)에 연결된 프론트엔드를
// jsdom으로 렌더링해 실제 fetch 통신까지 포함한 end-to-end 검증을 수행한다.
const path = require("path");
const fs = require("fs");
const { JSDOM } = require("jsdom");

let pass = 0, fail = 0;
function assert(cond, msg) { if (cond) { pass++; console.log("  ✅", msg); } else { fail++; console.error("  ❌", msg); } }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
const ORIGIN = "http://localhost:4603";
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

  console.log("\n[1] app.html 로드(토큰 보유) + 서버 상태/사용자 표시 + 기본 화면이 가이드인지 확인");
  const appPage = loadPage("app.html");
  appPage.window.localStorage.setItem("kfi_token", issuedToken);
  evalFile(appPage.window, "js/common.js");
  evalFile(appPage.window, "js/app.js");
  const $ = (id) => appPage.doc.getElementById(id);
  const win = appPage.window;
  await sleep(300);
  assert($("noticeBox").textContent.includes("MOCK"), "헬스체크 결과가 화면에 반영됨(MOCK 모드 표시)");
  assert($("whoami").textContent.includes("fe-test@example.com"), "로그인 사용자 표시됨");
  assert(win.document.getElementById("view-guide").classList.contains("active"), "로그인 직후 기본 화면은 서비스 가이드");
  assert($("pageTitle").textContent.includes("서비스 가이드"), "상단 타이틀도 서비스 가이드로 표시됨");

  console.log("\n[2] 가이드 화면에서 1부로 이동 (퀵점프 칩으로 공문 판별 카드까지 스크롤)");
  win.jumpTo("part1", "card-doc");
  assert(win.document.getElementById("view-part1").classList.contains("active"), "가이드에서 1부로 정상 전환됨");

  console.log("\n[3] 1부 흐름 (한 페이지 안에서 순서대로 입력, 실서버 API 통신)");
  $("docText").value = "리튬이온 전용 소화기를 즉시 비치하지 않으면 과태료가 부과됩니다. 오늘까지 계좌로 입금 바랍니다.";
  await win.analyzeDoc();
  await sleep(100);
  assert($("docResult").textContent.includes("고위험"), "문서판별 결과: 고위험 표시");
  assert($("docResult").innerHTML.includes('<mark class="hl">'), "의심 문구가 하이라이트(mark 태그)됨");

  $("docText").value = "본 문서는 2026년 리튬이온 전용소화기 비치 안내문(제2026-118호)입니다. 관할 소방서(02-000-0000)로 문의 바랍니다.";
  await win.analyzeDoc();
  $("approvalNumber").value = "성능인증 제2023-7-118호";
  await win.checkApproval();
  $("sellerName").value = "대한안전산업(주)";
  await win.checkSeller();
  await sleep(100);
  assert($("approvalResult").textContent.includes("정상 등록"), "승인번호 결과: 정상 등록 표시");
  assert($("sellerResult").textContent.includes("등록"), "판매자 결과: 등록업체 표시");
  assert($("verdictBoxA").textContent.includes("특이 위험이 없습니다"), "1부 종합판정: 안전 (같은 페이지에서 실시간 갱신됨)");
  assert($("bridgeCTA").className.includes("show"), "브릿지 CTA 노출됨");

  console.log("\n[4] 2부 이동: 유닛 조회 -> 자동 등록 -> 내 소화기함 반영");
  win.switchView("part2");
  $("unitCode").value = "EYTN-52981";
  await win.evaluateAndShow();
  await sleep(300);
  assert($("unitInfoResult").textContent.includes("내 소화기함에 등록됨"), "유닛 조회 시 자동 등록 문구 표시");
  assert($("verdictBoxB").textContent.includes("정상 사용 가능"), "2부 종합판정: 안전");
  await sleep(200);
  assert($("lockerList").textContent.includes("EYTN-52981"), "내 소화기함 목록에 등록된 유닛 표시");
  assert($("lockerList").innerHTML.includes("safe"), "내 소화기함 배지가 safe(안전) 상태");

  console.log("\n[5] 신고 접수");
  await win.reportMaint();
  await sleep(200);

  console.log("\n[6] 리콜 시뮬레이션 -> 알림 -> 내 소화기함/1부 재조회 자동 반영");
  win.switchView("part1");
  $("approvalNumber").value = "성능인증 제2023-7-118호";
  await win.checkApproval();
  await win.simulateRecallEvent();
  await sleep(400);
  assert($("recallAlert").className.includes("show"), "리콜 배너 노출됨");
  assert($("recallAlert").textContent.includes("영향받은 사용자 1명"), "영향받은 사용자 수 표시(1명)");
  assert($("approvalResult").textContent.includes("취소"), "1부 승인번호 결과도 취소 상태로 자동 갱신됨(재조회 트리거)");
  win.switchView("part2");
  assert($("lockerList").innerHTML.includes("danger"), "내 소화기함이 리콜 후 danger(위험) 배지로 갱신됨");
  win.switchView("notif");
  await sleep(200);
  assert($("notifList").textContent.includes("리콜"), "알림 목록에 리콜 메시지 표시");
  assert($("notifCount").textContent !== "0" && $("notifCount").style.display !== "none", "사이드바 알림 배지에 카운트 표시됨");

  console.log("\n[7] 관제 대시보드");
  win.switchView("admin");
  await sleep(300);
  assert(parseInt($("statMaint").textContent) >= 1, "관제 대시보드에 점검요청 통계 반영 (statMaint=" + $("statMaint").textContent + ")");
  assert(!$("reportTableBody").textContent.includes("불러오는 중"), "최근 접수 내역 테이블이 로딩 상태를 벗어나 실데이터로 채워짐");

  console.log(`\n=== 프론트엔드 E2E 결과: ${pass}건 통과, ${fail}건 실패 ===`);
  process.exit(fail === 0 ? 0 : 1);
}

main().catch((e) => { console.error("테스트 실행 중 예외:", e); process.exit(1); });
