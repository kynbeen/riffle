"use strict";

// 웹 앱 설치(PWA)용 서비스 워커. 화면 파일만 저장해 두고, 문서 작업(/api/)과 사용자별 응답은 절대 저장하지 않는다.
// 빌드 파일 이름은 빌드마다 바뀌므로 미리 목록을 두지 않고 받아 온 것을 저장한다(네트워크 먼저, 끊기면 저장본).
// 이름을 바꾸면 옛 화면(riffle-shell-*)이 저장해 둔 것은 activate 에서 지워진다.
const CACHE_NAME = "riffle-ui-v1";

self.addEventListener("install", (event) => {
  // 첫 화면("/")은 접속자마다 작업공간 쿠키를 싣는 응답이라 미리 저장하지 않는다.
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(["/manifest.webmanifest"])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
    )),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  event.respondWith((async () => {
    try {
      const response = await fetch(event.request);
      // 서버가 사용자별 응답이라고 표시한 것은 저장하지 않는다. 첫 화면은 세션 쿠키를 발급하는 응답이라 여기 걸린다.
      const noStore = (response.headers.get("Cache-Control") || "").includes("no-store");
      if (response.ok && !noStore) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(event.request, response.clone());
      }
      return response;
    } catch (error) {
      const cached = await caches.match(event.request, { ignoreSearch: true });
      if (cached) return cached;
      throw error;
    }
  })());
});
