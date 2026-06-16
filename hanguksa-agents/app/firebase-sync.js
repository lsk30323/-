/* 한능검 2급 합격 마스터 — Firebase 실계정 + 클라우드 동기화 (선택 기능)
 *
 * ▶ 활성화: 아래 HG2_FIREBASE_CONFIG 에 Firebase 웹 앱 config 객체를 붙여넣으세요.
 *   (설정 방법은 FIREBASE_SETUP.md 참고)
 * ▶ 미설정(null)이면 앱은 기존처럼 100% 로컬(기기 내 저장)로 동작합니다.
 *   이 파일은 그 경우 아무 것도 로드/실행하지 않습니다.
 */
window.HG2_FIREBASE_CONFIG = null;
/* 예시:
window.HG2_FIREBASE_CONFIG = {
  apiKey: "AIza...",
  authDomain: "your-project.firebaseapp.com",
  projectId: "your-project",
  storageBucket: "your-project.appspot.com",
  messagingSenderId: "1234567890",
  appId: "1:1234567890:web:abcdef"
};
*/

(function () {
  "use strict";
  var API = { enabled: false };
  window.HG2SYNC = API;

  var cfg = window.HG2_FIREBASE_CONFIG;
  if (!cfg) return; // 미설정 → 로컬 모드(아무 것도 안 함)

  var VER = "10.12.2";
  var BASE = "https://www.gstatic.com/firebasejs/" + VER + "/";
  function load(src) {
    return new Promise(function (res, rej) {
      var s = document.createElement("script");
      s.src = src; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
  }

  load(BASE + "firebase-app-compat.js")
    .then(function () {
      return Promise.all([
        load(BASE + "firebase-auth-compat.js"),
        load(BASE + "firebase-firestore-compat.js"),
      ]);
    })
    .then(function () {
      firebase.initializeApp(cfg);
      API.auth = firebase.auth();
      API.db = firebase.firestore();
      API.enabled = true;
      API.auth.onAuthStateChanged(function (u) {
        if (typeof API._onUser === "function") API._onUser(u);
      });
      if (typeof API._onReady === "function") API._onReady();
    })
    .catch(function (e) {
      console.warn("[HG2SYNC] Firebase 로드 실패(오프라인이거나 차단됨):", e);
    });

  // ---- 공개 API (앱에서 호출) ----
  API.onUser = function (cb) { API._onUser = cb; };
  API.onReady = function (cb) { if (API.enabled) cb(); else API._onReady = cb; };
  API.signInGoogle = function () {
    var p = new firebase.auth.GoogleAuthProvider();
    return API.auth.signInWithPopup(p);
  };
  API.signUpEmail = function (em, pw) { return API.auth.createUserWithEmailAndPassword(em, pw); };
  API.signInEmail = function (em, pw) { return API.auth.signInWithEmailAndPassword(em, pw); };
  API.signOut = function () { return API.auth.signOut(); };
  API.pull = function (uid) {
    return API.db.collection("users").doc(uid).get().then(function (d) {
      return d.exists ? d.data() : null;
    });
  };
  var pushT;
  API.push = function (uid, data) {
    clearTimeout(pushT);
    pushT = setTimeout(function () {
      API.db.collection("users").doc(uid).set(data, { merge: true }).catch(function () {});
    }, 1500);
  };
})();
