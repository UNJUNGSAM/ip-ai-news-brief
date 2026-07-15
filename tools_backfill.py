# -*- coding: utf-8 -*-
"""기존 수집 데이터의 구글뉴스 중계링크를 원문 URL로 복원하고 본문을 보충하는 1회성 도구.
실행: python tools_backfill.py"""
import json
import time
from pathlib import Path

from data_pipeline import (
    resolve_gnews_link, fetch_article_body, first_sentences,
    extract_keywords, DATA_DIR,
)

def main():
    for f in sorted(DATA_DIR.glob("news_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        fixed_link, fixed_body = 0, 0
        for a in data:
            link = a.get("link", "")
            if "news.google.com" in link:
                real = resolve_gnews_link(link)
                time.sleep(0.1)
                if real:
                    a["link"] = real
                    fixed_link += 1
                    if len(a.get("content", "")) < 100:
                        body = fetch_article_body(real)
                        if body:
                            a["content"] = body
                            a["summary"] = first_sentences(body, 3)
                            a["keywords"] = extract_keywords(a["title"] + " " + a["summary"])
                            fixed_body += 1
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{f.name}: 링크 복원 {fixed_link}건, 본문 보충 {fixed_body}건")

if __name__ == "__main__":
    main()
