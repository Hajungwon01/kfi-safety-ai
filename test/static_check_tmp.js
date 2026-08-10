const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

let pass = 0, fail = 0;
function assert(cond, msg) { if (cond) { pass++; console.log("  ✅", msg); } else { fail++; console.error("  ❌", msg); } }

const PUBLIC = "/sessions/awesome-exciting-planck/mnt/KFI/구현프로젝트_FastAPI/public";
let html = fs.readFileSync(path.join(PUBLIC, "app.html"), "utf-8");
html = html.replace(/<script src="https:\/\/cdn\.jsdelivr\.net[^>]*><\/script>/, "");
const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/app.html" });
const doc = dom.window.document;

// 구조 검증: 사이드바가 5개 항목(가이드/1부/내 소화기 관리/관제/알림)으로 줄었는지
const navItems = [...doc.querySelectorAll(".navitem")].map(el => el.dataset.view);
assert(JSON.stringify(navItems) === JSON.stringify(["guide","part1","part2","admin","notif"]), "사이드바가 5개 항목으로 정리됨: " + navItems.join(","));

// view-part1 안에 4개 카드가 전부 들어있는지 (분리된 view-doc/approval/seller/verdict1이 없는지)
["view-doc","view-approval","view-seller","view-verdict1"].forEach(id => {
  assert(doc.getElementById(id) === null, `${id}는 더 이상 존재하지 않음(단일 페이지로 병합됨)`);
});
assert(doc.getElementById("view-part1") !== null, "view-part1(단일 병합 페이지)이 존재함");
["card-doc","card-approval","card-seller","card-verdict1"].forEach(id => {
  assert(doc.querySelector("#view-part1 #" + id) !== null, `${id} 카드가 view-part1 안에 위치함`);
});

// 퀵점프 칩이 올바른 앵커를 가리키는지
const jumpButtons = [...doc.querySelectorAll("#view-part1 button")].filter(b => b.getAttribute("onclick") && b.getAttribute("onclick").startsWith("jumpTo("));
assert(jumpButtons.length === 4, "퀵점프 칩 4개(①~④) 존재: " + jumpButtons.length + "개");
const anchors = jumpButtons.map(b => b.getAttribute("onclick").match(/'card-[a-z0-9]+'/)[0]);
assert(JSON.stringify(anchors) === JSON.stringify(["'card-doc'","'card-approval'","'card-seller'","'card-verdict1'"]), "퀵점프 칩 순서/타깃이 doc→approval→seller→verdict1 순서로 일치함");

// 가이드 페이지 1부 카드도 jumpTo를 사용하는지 (더 이상 switchView('doc') 등을 쓰지 않는지)
assert(!html.includes("switchView('doc')") && !html.includes("switchView('approval')") && !html.includes("switchView('seller')") && !html.includes("switchView('verdict1')"), "가이드 카드도 더 이상 분리된 view로 전환하지 않음(jumpTo로 대체됨)");

// app.js 쪽 검증
const appJs = fs.readFileSync(path.join(PUBLIC, "js/app.js"), "utf-8");
assert(/function jumpTo\(/.test(appJs), "app.js에 jumpTo() 함수 정의됨");
assert(/part1:\s*"구매 · 거래 단계"/.test(appJs), "VIEW_TITLES에 part1 타이틀이 정상 등록됨");
assert(!/doc:\s*"/.test(appJs) && !/approval:\s*"승인번호 조회"/.test(appJs), "VIEW_TITLES에서 doc/approval/seller/verdict1 항목이 제거됨");

// 데모 문구 재확인
assert(!html.includes("(데모)") && !html.includes("관리자 데모"), "화면 텍스트에 '데모' 표현이 없음");

console.log(`\n=== 정적 구조 검증 결과: ${pass}건 통과, ${fail}건 실패 ===`);
process.exit(fail === 0 ? 0 : 1);
