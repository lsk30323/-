import type { Difficulty } from '@/db/schema';
import { buildUserPromptHeader, type TopicPromptModule } from './_shared';

const topicSystemPrompt = `토픽: **Foreground Service**

핵심 개념:
- \`Service\` lifecycle: \`onStartCommand\` 반환값 (\`START_STICKY\` vs \`START_REDELIVER_INTENT\`).
- \`startForeground(id, notification, foregroundServiceType)\` — Android 14+ 부터
  \`foregroundServiceType\` 명시 필수, manifest와 일치 필요.
- \`foregroundServiceType\`: \`location\`, \`health\`, \`dataSync\` 등 — 만보기 앱은 보통
  \`health\` 또는 \`location\`. 14+에서 정확한 매핑 안 하면 SecurityException.
- Notification: \`NotificationChannel\` (importance), foreground notification은 사용자가
  swipe로 dismiss 못 함. 본 알림은 minimal (배터리 사용 표시).
- Doze / App Standby Buckets / Battery Optimization 화이트리스트 정책 — 사용자가
  앱을 백그라운드 빌려두어도 walk session이 살아있어야 한다.
- \`BOOT_COMPLETED\` BroadcastReceiver로 디바이스 재부팅 후 service 자동 재시작.
- WorkManager (\`OneTimeWorkRequest\`, \`PeriodicWorkRequest\`) vs ForegroundService —
  실시간 카운팅은 FGS, 주기 동기화는 WorkManager.
- Sensor 이벤트 스트림 (\`SensorManager\`, \`Step Counter\` / \`Step Detector\`)을 service
  scope coroutine에서 collect하고 ViewModel/DB로 흘려보내는 pipeline.

흔한 함정 / 평가 포인트:
- \`startForegroundService\` 호출 후 5초 내 \`startForeground\`를 부르지 않으면 ANR/crash.
- 14+ 백그라운드에서 FGS 시작 제약 (UI/사용자 액션 또는 일부 면제 케이스만 허용).
- \`PARTIAL_WAKE_LOCK\` 남용 — 배터리 이슈, 보통 FGS만으로 충분.
- 권한: \`FOREGROUND_SERVICE\`, \`FOREGROUND_SERVICE_HEALTH\`, \`POST_NOTIFICATIONS\` (13+),
  \`ACTIVITY_RECOGNITION\` (걸음 수 센서 접근).

출제 시 고려:
- 입문: notification + start/stop FGS 골격, manifest 권한 명시.
- 중급: 센서 stream → DB pipeline + 재부팅 후 자동 재시작 + Doze 대응.
- 면접급: WorkManager와 역할 분리, 권한 14+ 변경 사항, 사용자 거부 시 graceful 종료.
`;

function buildUserPrompt(difficulty: Difficulty): string {
  return `${buildUserPromptHeader('foreground-service', difficulty)}

추가 지시:
- description에 만보기 service의 실제 사용 맥락(예: "걸음 수 센서를 백그라운드에서도
  지속 카운트하기 위해…")을 포함하세요.
- reference_solution은 \`Service\` 서브클래스 + \`AndroidManifest.xml\` 발췌(권한·service 선언)를
  같이 보여주세요. notification channel 코드도 포함.
- Android 14+ \`foregroundServiceType\` 매칭과 권한 변경을 description 또는 reference에서
  명시적으로 다루세요. 면접급은 stage 2(tradeoff)에서 FGS vs WorkManager 비교 필수.`;
}

export const foregroundServicePrompt: TopicPromptModule = {
  topic: 'foreground-service',
  topicSystemPrompt,
  buildUserPrompt,
};
