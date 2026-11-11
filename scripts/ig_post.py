"""thedealnoteup 인스타 게시 (편집장이 GitHub Actions에서 직접 실행할 때만 돈다).

게시물 폴더(공개 미디어 저장소의 GitHub Pages)에 post.json이 있다:
  {"type": "carousel" | "image" | "reel", "media": ["01.jpg", ...], "caption": "..."}
사용: python scripts/ig_post.py <폴더 이름 또는 URL> [--publish]   (예: 2026-11-11-live-reel)
--publish 없이 돌리면 토큰·파일만 확인하고 아무것도 올리지 않는다.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PAGES = "https://taegil-lee.github.io/thedealnoteup-media"
HOSTS = ("https://graph.instagram.com", "https://graph.facebook.com")  # 토큰 종류에 따라 받는 쪽이 다르다


def http(method, url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method=method), timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as err:  # 토큰이 들어간 URL은 찍지 않는다
        detail = json.loads(err.read() or b"{}").get("error", {}).get("message", "")
        raise RuntimeError(f"{method} {urllib.parse.urlsplit(url).path} → {err.code} {detail}") from None


def load_post(folder):
    post = http("GET", f"{folder.rstrip('/')}/post.json")
    kind, media, cap = post.get("type"), post.get("media") or [], post.get("caption", "")
    if kind not in ("carousel", "image", "reel"):
        raise ValueError(f"type은 carousel/image/reel 중 하나: {kind!r}")
    if not media or (kind != "carousel" and len(media) != 1) or (kind == "carousel" and not 2 <= len(media) <= 20):
        raise ValueError(f"{kind}에 맞지 않는 사진 수: {len(media)}")
    if kind == "reel" and not media[0].endswith(".mp4") or kind != "reel" and not all(m.endswith(".jpg") for m in media):
        raise ValueError("릴스는 .mp4, 사진은 .jpg만 (인스타 API는 PNG를 안 받는다)")
    if len(cap) > 2200 or cap.count("#") > 30:
        raise ValueError("캡션은 2,200자·해시태그 30개 이하")
    return kind, [f"{folder.rstrip('/')}/{m}" for m in media], cap


def find_host(token, ig_id):
    for host in HOSTS:
        try:
            me = http("GET", f"{host}/{ig_id}?fields=username&access_token={token}")
            return host, me["username"]
        except RuntimeError as err:
            print(f"  {host}: {err}")
    raise SystemExit("✗ 토큰으로 인스타 계정을 읽지 못함 (IG_ACCESS_TOKEN, IG_USER_ID 확인)")


def wait_ready(api, cid, token):
    for _ in range(30):  # 최대 5분 (문서 권장)
        status = http("GET", f"{api}/{cid}?fields=status_code&access_token={token}")["status_code"]
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"인스타가 파일 처리에 실패: {status}")
        time.sleep(10)
    raise RuntimeError("5분 안에 처리가 끝나지 않음")


def publish(api, ig_id, token, kind, urls, cap):
    media = f"{api}/{ig_id}/media"
    if kind == "image":
        cid = http("POST", media, {"image_url": urls[0], "caption": cap, "access_token": token})["id"]
    elif kind == "reel":
        cid = http("POST", media, {"media_type": "REELS", "video_url": urls[0], "caption": cap,
                                   "share_to_feed": "true", "access_token": token})["id"]
    else:
        kids = [http("POST", media, {"image_url": u, "is_carousel_item": "true", "access_token": token})["id"] for u in urls]
        for k in kids:
            wait_ready(api, k, token)
        cid = http("POST", media, {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": cap,
                                   "access_token": token})["id"]
    wait_ready(api, cid, token)
    post_id = http("POST", f"{api}/{ig_id}/media_publish", {"creation_id": cid, "access_token": token})["id"]
    return http("GET", f"{api}/{post_id}?fields=permalink&access_token={token}").get("permalink", post_id)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    folder, go = sys.argv[1].strip().rstrip("/"), "--publish" in sys.argv
    if not folder.startswith("http"):  # 이 저장소의 폴더 이름만 줘도 공개 주소로 바꾼다
        folder = f"{PAGES}/{folder}"
    token, ig_id = os.environ.get("IG_ACCESS_TOKEN"), os.environ.get("IG_USER_ID")
    if not token or not ig_id:
        raise SystemExit("✗ IG_ACCESS_TOKEN / IG_USER_ID 없음")
    kind, urls, cap = load_post(folder)
    print(f"✓ post.json: {kind} {len(urls)}개, 캡션 {len(cap)}자")
    for u in urls:  # 인스타가 가져가기 전에 공개 주소가 열리는지 먼저 본다
        with urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=30) as r:
            print(f"  ✓ {u.rsplit('/', 1)[-1]} ({r.headers.get('Content-Type')})")
    host, name = find_host(token, ig_id)
    print(f"✓ 계정 @{name} ({host})")
    if not go:
        print("확인만 함 — 게시하려면 mode를 publish로 다시 실행")
        return
    print(f"✓ 게시 완료: {publish(host, ig_id, token, kind, urls, cap)}")


if __name__ == "__main__":
    main()
