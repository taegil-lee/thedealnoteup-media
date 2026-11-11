"""thedealnoteup 댓글 → DM 봇. GitHub Actions가 5분마다 돌린다.

최근 게시물의 댓글 중 키워드('세일')가 들어간 댓글에, 그 게시물에 맞는 노션 링크를 DM(비공개 답장)으로 1번 보낸다.
- 게시물별 링크: dm.json (게시물 주소의 /p/·/reel/ 뒤 코드 → 링크, 없으면 default)
- 이미 보낸 댓글: state/replied.txt (댓글 ID의 해시만 저장. 공개 저장소라 이름·내용은 남기지 않는다)
- 로그에도 댓글 단 사람과 내용은 찍지 않는다.
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
STATE = ROOT / "state" / "replied.txt"
HOSTS = ("https://graph.instagram.com", "https://graph.facebook.com")


def http(method, url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method=method), timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as err:  # 토큰이 든 URL은 찍지 않는다
        detail = json.loads(err.read() or b"{}").get("error", {}).get("message", "")
        raise RuntimeError(f"{method} {urllib.parse.urlsplit(url).path.split('/')[-1]} → {err.code} {detail}") from None


def key(comment_id):
    return hashlib.sha256(comment_id.encode()).hexdigest()[:16]


def shortcode(permalink):
    parts = [p for p in urllib.parse.urlsplit(permalink or "").path.split("/") if p]
    return parts[-1] if parts else ""


def wants_link(comment, keyword, me):
    return keyword in (comment.get("text") or "") and comment.get("username") != me


def message(cfg, link):
    return cfg["message"].replace("{link}", link)


def main():
    cfg = json.loads((ROOT / "dm.json").read_text(encoding="utf-8"))
    token, ig_id = os.environ.get("IG_ACCESS_TOKEN"), cfg["ig_user_id"]
    if not token:
        sys.exit("✗ IG_ACCESS_TOKEN 없음 (저장소 Settings → Secrets에 넣기)")
    for api in HOSTS:  # 토큰 종류에 따라 받는 쪽이 다르다
        try:
            me = http("GET", f"{api}/{ig_id}?fields=username&access_token={token}")["username"]
            break
        except RuntimeError:
            continue
    else:
        sys.exit("✗ 토큰으로 계정을 읽지 못함")
    done = set(STATE.read_text().split()) if STATE.exists() else set()
    sent = failed = 0
    media = http("GET", f"{api}/{ig_id}/media?fields=id,permalink&limit={cfg.get('recent', 10)}&access_token={token}")
    for m in media.get("data", []):
        link = cfg["links"].get(shortcode(m.get("permalink")), cfg["links"]["default"])
        # shortcut: 게시물당 최근 댓글 50개만 본다, 댓글이 더 많아지면 페이지 넘김 추가
        comments = http("GET", f"{api}/{m['id']}/comments?fields=id,text,username&limit=50&access_token={token}")
        for c in comments.get("data", []):
            if key(c["id"]) in done or not wants_link(c, cfg["keyword"], me):
                continue
            try:
                http("POST", f"{api}/{ig_id}/messages?access_token={token}",
                     {"recipient": json.dumps({"comment_id": c["id"]}),
                      "message": json.dumps({"text": message(cfg, link)}, ensure_ascii=False)})
                sent += 1
            except RuntimeError as err:  # 7일 지난 댓글 등은 다시 시도해도 안 되니 기록하고 넘어간다
                print(f"  DM 실패: {err}")
                failed += 1
            done.add(key(c["id"]))
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text("\n".join(sorted(done)) + "\n")
    print(f"✓ @{me}: 게시물 {len(media.get('data', []))}개 확인, DM {sent}건 보냄, 실패 {failed}건")


def selftest():
    assert shortcode("https://www.instagram.com/reel/AbC123/") == "AbC123"
    assert wants_link({"text": "세일 정보 주세요", "username": "a"}, "세일", "me")
    assert not wants_link({"text": "세일", "username": "me"}, "세일", "me")
    assert not wants_link({"text": "예뻐요"}, "세일", "me")
    assert message({"message": "링크 {link}"}, "L") == "링크 L"
    assert key("1") == key("1") != key("2")
    print("selftest ok")


if __name__ == "__main__":
    selftest() if "--test" in sys.argv else main()
