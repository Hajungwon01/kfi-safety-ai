// 챗봇(프론트, app.html) <-> 실제 FastAPI 서버(/api/chat) 통합 검증.
// 앱은 챗봇 하나로 운영되므로, 여기서는 프리셋 카드 안내문구/OCR 아이콘/채팅 버블 안에서
// 바로 신고를 접수하는 흐름처럼 "챗봇 UI 세부 동작"을 검증한다. 화면 전환·권한 가드는
// frontend_e2e.js에서 다룬다.
const path = require("path");
const fs = require("fs");
const { JSDOM } = require("jsdom");

let pass = 0, fail = 0;
function assert(cond, msg) { if (cond) { pass++; console.log("  ✅", msg); } else { fail++; console.error("  ❌", msg); } }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
const ORIGIN = "http://localhost:4601";
const PUBLIC = path.join(__dirname, "..", "public");

async function main() {
  let html = fs.readFileSync(path.join(PUBLIC, "app.html"), "utf-8");
  html = html.replace(/<script src="https:\/\/cdn\.jsdelivr\.net[^>]*><\/script>/, "");

  const dom = new JSDOM(html, { runScripts: "dangerously", url: ORIGIN + "/app.html" });
  const { window } = dom;
  window.fetch = (input, init) => {
    const url = (typeof input === "string" && input.startsWith("/")) ? ORIGIN + input : input;
    return fetch(url, init);
  };
  window.alert = () => {};
  window.HTMLElement.prototype.scrollIntoView = () => {};

  // 실제 회원가입 API를 호출해 진짜 토큰을 발급받아 인증 가드를 통과시킨다.
  const regRes = await fetch(ORIGIN + "/api/auth/register", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "widget-test@example.com", password: "pw1234" }),
  });
  const regBody = await regRes.json();
  window.localStorage.setItem("kfi_token", regBody.token);

  const commonJs = fs.readFileSync(path.join(PUBLIC, "js", "common.js"), "utf-8");
  window.eval(commonJs);
  const appJs = fs.readFileSync(path.join(PUBLIC, "js", "app.js"), "utf-8");
  window.eval(appJs);
  await sleep(200);

  const doc = window.document;
  const $ = (id) => doc.getElementById(id);

  console.log("\n[1] 챗봇은 항상 열려있는 메인 화면(더 이상 토글 위젯이 아님)");
  assert(doc.getElementById("view-chat").classList.contains("active"), "로그인 직후 챗봇 화면이 기본으로 열려있음");
  assert(!!$("chatBody") && !!$("chatInput"), "채팅창/입력창이 렌더링됨");

  console.log("\n[2] 프리셋 카드 6개 각각 클릭 시, 실행 대신 입력창에 완성형 문구만 채워짐");
  const presetLabels = ["공문 판별", "승인번호 조회", "업체 확인", "소화기 조회·등록", "내 소화기함 보기", "내 알림 확인"];
  const cards = $("presetGrid").querySelectorAll(".preset-card");
  assert(cards.length === presetLabels.length, `프리셋 카드 개수가 ${presetLabels.length}개`);
  presetLabels.forEach((label, i) => {
    assert(cards[i].textContent.includes(label), `${i}번째 프리셋 카드 라벨: ${label}`);
  });
  const photoSupportedIdx = [0, 3]; // 공문 판별, 소화기 조회·등록만 사진(OCR) 업로드도 가능
  presetLabels.forEach((label, i) => {
    const hasBadge = !!cards[i].querySelector(".photo-badge");
    const expected = photoSupportedIdx.includes(i);
    assert(hasBadge === expected, `${label} 카드의 사진 업로드 가능 표시(📷 배지)가 ${expected ? "있음" : "없음"}`);
  });
  const before = $("chatBody").children.length;
  window.usePreset(4); // 내 소화기함 보기
  assert($("chatBody").children.length === before, "프리셋 클릭은 채팅 말풍선을 추가하지 않고 API도 직접 호출하지 않음");
  assert($("chatInput").value === "내 소화기함 보여줘", "소화기함 프리셋은 입력창에 바로 전송 가능한 완성 문구를 채움(빈칸 없음)");

  window.usePreset(1); // 승인번호 조회 (빈칸이 있는 템플릿)
  assert($("chatInput").value === "형식승인 제0000-0-000호 진짜예요?", "승인번호 프리셋은 빈칸이 포함된 예시 문구를 채움");
  const sel = [$("chatInput").selectionStart, $("chatInput").selectionEnd];
  assert($("chatInput").value.slice(sel[0], sel[1]) === "형식승인 제0000-0-000호", "빈칸 부분이 선택 상태라 바로 타이핑해서 채울 수 있음");

  console.log("\n[3] 사진(OCR) 업로드 아이콘이 채팅 입력창 옆에 있음");
  const imgInput = $("chatImage");
  assert(!!imgInput && imgInput.type === "file" && imgInput.accept === "image/*", "OCR용 이미지 업로드 input이 올바르게 존재함");

  console.log("\n[3-1] 프리셋 빈칸을 채우지 않고 그대로 전송하면, 엉뚱한 답 대신 실제 값/사진 업로드 안내가 뜸");
  window.usePreset(3); // 소화기 조회·등록 (빈칸: 합격표시번호)
  assert($("chatInput").value === "합격표시번호 조회해줘", "소화기 프리셋 빈칸을 채우지 않은 상태");
  await window.sendChat();
  await sleep(200);
  let hintMsg = $("chatBody").lastChild;
  assert(hintMsg.textContent.includes("채워지지 않았어요"), "빈칸 미입력 상태를 감지해 안내함(LLM 폴백 아님)");
  assert(hintMsg.textContent.includes("📷"), "사진 업로드 버튼을 대안으로 안내함");

  console.log("\n[4] 빠른질문 버튼 -> 서버 호출 -> retrieval-only 카드 렌더링");
  await window.askQuick("소화기 내용연수 지나면 어떻게 되나요?");
  await sleep(300);
  let bodyHtml = $("chatBody").innerHTML;
  assert(bodyHtml.includes("소화기 내용연수 지나면 어떻게 되나요?"), "사용자 질문이 대화창에 표시됨");
  assert(bodyHtml.includes("src-card"), "검색된 참고자료 카드가 렌더링됨(retrieval-only 모드)");
  assert(bodyHtml.includes("내용연수"), "참고자료 내용에 '내용연수' 관련 텍스트 포함");

  console.log("\n[5] 채팅창에 승인번호를 그냥 문장으로 입력해도 조회가 실제로 실행됨(tool 모드)");
  $("chatInput").value = "형식승인 제9999-9-999호 확인해줘";
  await window.sendChat();
  await sleep(300);
  let last = $("chatBody").lastChild;
  assert(last.textContent.includes("채팅으로 바로 조회함"), "채팅 메시지만으로 실제 조회가 실행됐다는 표시가 뜸");
  assert(last.textContent.includes("등록되지 않은"), "미등록 승인번호로 조회 결과가 실제 DB 값 그대로 채팅으로 답변됨");

  console.log("\n[6] 위험한 조회 결과는 채팅 버블 안에서 바로 신고 접수까지 가능함");
  assert(last.innerHTML.includes("이 승인번호 신고하기"), "미등록 승인번호는 채팅 버블 안에 신고 버튼이 붙음");
  const reportBtn = last.querySelector("button.btn-report");
  assert(!!reportBtn, "신고 버튼 엘리먼트를 실제로 찾을 수 있음");
  const btnId = reportBtn.id;
  const idx = btnId.split("_")[1];
  await window.submitChatReport(Number(idx));
  await sleep(200);
  assert(doc.getElementById(btnId).disabled === true, "신고 접수 후 버튼이 비활성화됨");
  assert(doc.getElementById(btnId).textContent.includes("접수됨"), "신고 접수 후 버튼 문구가 접수됨으로 바뀜");
  // 신고가 실제로 서버에 저장됐는지는 admin 토큰으로 접수 목록을 조회해 확인한다.
  const adminLogin = await fetch(ORIGIN + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "admin@kfi.go.kr", password: "admin1234!" }) });
  const adminBody = await adminLogin.json();
  const repList = await (await fetch(ORIGIN + "/api/reports", { headers: { Authorization: "Bearer " + adminBody.token } })).json();
  assert(repList.some(r => r.target === "형식승인 제9999-9-999호"), "채팅에서 접수한 신고가 실제로 서버에 저장됨");

  console.log("\n[7] 채팅창에 합격표시번호를 입력하면 자동으로 내 소화기함에 등록되고, 채팅으로 다시 확인 가능");
  $("chatInput").value = "AXZG-45271 이거 조회해줘";
  await window.sendChat();
  await sleep(300);
  last = $("chatBody").lastChild;
  assert(last.textContent.includes("AXZG-45271") || last.textContent.includes("합격표시번호"), "채팅으로 소화기 조회 결과가 답변됨");

  $("chatInput").value = "내 소화기함 보여줘";
  await window.sendChat();
  await sleep(200);
  assert($("chatBody").lastChild.textContent.includes("AXZG-45271"), "채팅으로 조회한 소화기가 내 소화기함에 자동 등록되어 채팅으로 확인됨(loadLocker 대체)");

  console.log(`\n=== 챗봇 위젯 E2E 결과: ${pass}건 통과, ${fail}건 실패 ===`);
  process.exit(fail === 0 ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(1); });
