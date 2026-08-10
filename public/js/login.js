// 로그인/회원가입 페이지 전용 로직. 성공 시 app.html로 이동.
function setMsg(text, isError){
  const el = document.getElementById("authMsg");
  el.textContent = text;
  el.className = "msg" + (isError ? " error" : "");
}

async function doRegister(){
  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPassword").value;
  if (!email || !password) return setMsg("이메일/비밀번호를 입력하세요.", true);
  const r = await fetch("/api/auth/register", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ email, password }) });
  const body = await r.json();
  if (!r.ok) return setMsg("회원가입 실패: " + body.error, true);
  localStorage.setItem("kfi_token", body.token);
  setMsg("회원가입 완료! 이동 중...");
  redirectTo("/app.html");
}

async function doLogin(){
  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPassword").value;
  if (!email || !password) return setMsg("이메일/비밀번호를 입력하세요.", true);
  const r = await fetch("/api/auth/login", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ email, password }) });
  const body = await r.json();
  if (!r.ok) return setMsg("로그인 실패: " + body.error, true);
  localStorage.setItem("kfi_token", body.token);
  setMsg("로그인 완료! 이동 중...");
  redirectTo("/app.html");
}

// 이미 로그인된 상태로 이 페이지에 들어오면 바로 앱으로 보냄
(function redirectIfLoggedIn(){
  if (token()) redirectTo("/app.html");
})();
