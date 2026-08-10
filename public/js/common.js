// 공용 유틸 (모든 페이지에서 공유)
const API = "";
function token() { return localStorage.getItem("kfi_token") || ""; }
function authHeaders() { const t = token(); return t ? { Authorization: "Bearer " + t } : {}; }
function escapeHtml(s){ return (s||"").replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function parseJwt(t){ try { return JSON.parse(atob(t.split(".")[1])); } catch { return null; } }
function currentUser(){ const t = token(); return t ? parseJwt(t) : null; }
function redirectTo(path){ window.location.href = path; }
function logout(){ localStorage.removeItem("kfi_token"); redirectTo("/login.html"); }
// app.html 등 로그인이 필요한 페이지 맨 위에서 호출: 토큰 없으면 로그인 페이지로 보냄
function requireAuthOrRedirect(){
  if (!token()) { redirectTo("/login.html"); return false; }
  return true;
}
