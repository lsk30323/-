# Firebase 실계정 + 클라우드 동기화 켜는 법

설정하면 **구글/이메일 실로그인 + 기기 간 동기화**(Firestore 저장)가 켜집니다.
설정 전에는 앱이 기존처럼 **로컬(기기 내 저장)** 로 동작합니다.

> ⚠️ 제(어시스턴트) 환경은 외부 접속이 막혀 실제 로그인/동기화를 테스트하지 못했습니다.
> 아래대로 설정한 뒤 **본인 기기에서 동작 확인**해 주세요. 문제가 있으면 알려주시면 함께 고칩니다.

## 1) Firebase 프로젝트 만들기
1. <https://console.firebase.google.com> → **프로젝트 추가**
2. 좌측 **빌드 → Authentication → 시작하기**
   - **Sign-in method** 탭 → **Google** 사용 설정, **이메일/비밀번호** 사용 설정
   - **Settings → 승인된 도메인**에 배포 도메인 추가: `lsk30323.github.io`
3. 좌측 **빌드 → Firestore Database → 데이터베이스 만들기**(프로덕션 모드)
   - **규칙(Rules)** 탭에 아래를 붙여넣고 게시:
     ```
     rules_version = '2';
     service cloud.firestore {
       match /databases/{database}/documents {
         match /users/{uid} {
           allow read, write: if request.auth != null && request.auth.uid == uid;
         }
       }
     }
     ```
     (각 사용자가 **자기 문서만** 읽고 쓰게 제한 — 안전)

## 2) 웹 앱 config 복사
1. 프로젝트 설정(톱니) → **내 앱 → 웹 앱(`</>`) 추가** → 앱 등록
2. 표시되는 `firebaseConfig` 객체를 복사

## 3) 앱에 붙여넣기
`docs/firebase-sync.js`(배포본) 상단의
```js
window.HG2_FIREBASE_CONFIG = null;
```
를 복사한 config로 교체:
```js
window.HG2_FIREBASE_CONFIG = {
  apiKey: "AIza...",
  authDomain: "your-project.firebaseapp.com",
  projectId: "your-project",
  storageBucket: "your-project.appspot.com",
  messagingSenderId: "1234567890",
  appId: "1:...:web:..."
};
```
저장 → 커밋/푸시(또는 새 세션에서 "이 파일 반영") → Pages 재배포.

## 4) 사용
- 앱 로그인 화면에 **Google / 이메일(비밀번호)** 로그인이 활성화됩니다.
- 로그인하면 점수·오답노트·북마크가 **Firestore(클라우드)** 에 저장되고, 다른 기기에서 같은 계정으로 로그인하면 **동기화**됩니다.
- 설정/계정 화면에서 로그아웃하면 로컬 게스트 모드로 돌아갑니다.

## 동작 원리(요약)
- `firebase-sync.js`가 config가 있을 때만 Firebase SDK를 동적 로드하고 `window.HG2SYNC` API를 제공합니다.
- 앱은 로그인 사용자(uid)별로 `users/{uid}` 문서에 `{results, wrong, bm}`를 저장(디바운스)하고, 로그인 시 클라우드 데이터를 불러옵니다.
- config가 없으면 이 파일은 즉시 종료되어 앱은 완전히 로컬로 작동합니다.
