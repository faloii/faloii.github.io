#!/usr/bin/env python3
"""
쿠팡 애플 브랜드샵 가격 모니터링 봇

Playwright를 사용하여 쿠팡 애플 브랜드샵 페이지에서
제품 가격을 수집하고, 정가 대비 할인율을 계산하여
JSON 파일로 저장합니다.

GitHub Actions에서 주기적으로 실행됩니다.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

# 설정
BRAND_SHOP_URL = "https://shop.coupang.com/apple/76487"
SEARCH_URLS = [
    "https://www.coupang.com/np/search?component=&q=Apple&channel=user&isPrice498498=true&page={page}",
]
DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "products.json"
KST = timezone(timedelta(hours=9))

# Apple 제품 키워드 (검색 필터용)
APPLE_KEYWORDS = [
    "iPhone", "아이폰",
    "iPad", "아이패드",
    "MacBook", "맥북",
    "iMac", "아이맥",
    "Mac Mini", "맥 미니", "Mac mini",
    "Mac Studio", "맥 스튜디오",
    "Mac Pro", "맥 프로",
    "Apple Watch", "애플워치", "애플 워치",
    "AirPods", "에어팟",
    "AirTag", "에어태그",
    "Apple TV", "애플 TV",
    "HomePod", "홈팟",
    "Apple Pencil", "애플 펜슬",
    "Magic Keyboard", "매직 키보드",
    "Magic Mouse", "매직 마우스",
    "Magic Trackpad", "매직 트랙패드",
    "Studio Display", "스튜디오 디스플레이",
    "Pro Display", "프로 디스플레이",
]


def is_apple_product(name):
    """Apple 정품 제품인지 확인합니다."""
    if not name:
        return False
    name_lower = name.lower()
    # 케이스/필름 등 액세서리 제외
    exclude = ["케이스", "필름", "거치대", "충전기", "케이블", "어댑터",
               "스트랩", "밴드만", "보호", "강화유리", "compatible", "호환"]
    for ex in exclude:
        if ex in name_lower:
            return False
    for kw in APPLE_KEYWORDS:
        if kw.lower() in name_lower:
            return True
    return False


def parse_price(text):
    """가격 문자열에서 숫자를 추출합니다."""
    if not text:
        return 0
    numbers = re.sub(r"[^\d]", "", text)
    try:
        return int(numbers) if numbers else 0
    except ValueError:
        return 0


def classify_category(name):
    """제품명으로 카테고리를 분류합니다."""
    if not name:
        return "기타"
    n = name.lower()
    if "iphone" in n or "아이폰" in n:
        return "iPhone"
    if "ipad" in n or "아이패드" in n:
        return "iPad"
    if "macbook" in n or "맥북" in n:
        return "MacBook"
    if "imac" in n or "아이맥" in n:
        return "iMac"
    if "mac mini" in n or "맥 미니" in n or "맥미니" in n:
        return "Mac mini"
    if "mac studio" in n or "맥 스튜디오" in n:
        return "Mac Studio"
    if "mac pro" in n or "맥 프로" in n:
        return "Mac Pro"
    if "apple watch" in n or "애플워치" in n or "애플 워치" in n:
        return "Apple Watch"
    if "airpods" in n or "에어팟" in n:
        return "AirPods"
    if "airtag" in n or "에어태그" in n:
        return "AirTag"
    if "apple tv" in n or "애플 tv" in n:
        return "Apple TV"
    if "homepod" in n or "홈팟" in n:
        return "HomePod"
    if "pencil" in n or "펜슬" in n:
        return "Apple Pencil"
    if "magic" in n or "매직" in n:
        return "액세서리"
    if "display" in n or "디스플레이" in n:
        return "디스플레이"
    return "기타"


def scroll_to_bottom(page, max_scrolls=15):
    """페이지를 끝까지 스크롤하여 지연 로딩 콘텐츠를 불러옵니다."""
    prev_height = 0
    for _ in range(max_scrolls):
        curr_height = page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.5)


def try_brand_shop(page):
    """브랜드샵 페이지에서 제품 정보를 추출합니다."""
    products = []
    print(f"[1/3] 브랜드샵 접근 시도: {BRAND_SHOP_URL}")

    try:
        page.goto(BRAND_SHOP_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        scroll_to_bottom(page)

        # 전략 1: JSON-LD
        products = extract_json_ld(page)
        if products:
            print(f"  -> JSON-LD에서 {len(products)}개 상품 발견")
            return products

        # 전략 2: 내장 JSON 데이터
        products = extract_embedded_json(page)
        if products:
            print(f"  -> 내장 JSON에서 {len(products)}개 상품 발견")
            return products

        # 전략 3: DOM 파싱
        products = extract_from_dom(page)
        if products:
            print(f"  -> DOM에서 {len(products)}개 상품 발견")
            return products

        # 디버그용 HTML 저장
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "debug_brandshop.html").write_text(
            page.content(), encoding="utf-8"
        )
        print("  -> 상품을 찾지 못함. debug_brandshop.html 저장됨")

    except Exception as e:
        print(f"  -> 브랜드샵 접근 실패: {e}")

    return products


def try_search(page):
    """쿠팡 검색으로 Apple 제품을 수집합니다."""
    products = []
    search_queries = [
        "Apple 아이폰", "Apple 아이패드", "Apple 맥북",
        "Apple 에어팟", "Apple 워치", "Apple Mac",
    ]

    print("[2/3] 쿠팡 검색으로 제품 수집 시도")

    for query in search_queries:
        url = f"https://www.coupang.com/np/search?component=&q={query}&channel=user"
        try:
            print(f"  검색: {query}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            scroll_to_bottom(page, max_scrolls=5)

            items = extract_search_results(page)
            apple_items = [p for p in items if is_apple_product(p["name"])]
            products.extend(apple_items)
            print(f"    -> {len(apple_items)}개 Apple 제품 발견")

            time.sleep(2)  # 요청 간 딜레이
        except Exception as e:
            print(f"    -> 검색 실패: {e}")

    return products


def extract_json_ld(page):
    """JSON-LD 스크립트에서 상품 정보를 추출합니다."""
    products = []
    try:
        scripts = page.query_selector_all('script[type="application/ld+json"]')
        for script in scripts:
            data = json.loads(script.inner_text())
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and item.get("@type") in ("Product", "ItemList"):
                    if item.get("@type") == "ItemList":
                        for elem in item.get("itemListElement", []):
                            p = parse_ld_product(elem.get("item", elem))
                            if p:
                                products.append(p)
                    else:
                        p = parse_ld_product(item)
                        if p:
                            products.append(p)
    except Exception:
        pass
    return products


def parse_ld_product(data):
    """JSON-LD Product를 파싱합니다."""
    try:
        offers = data.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = int(float(offers.get("price", 0)))
        high = int(float(offers.get("highPrice", 0)))
        return {
            "name": data.get("name", ""),
            "price": price,
            "originalPrice": high if high > price else price,
            "url": data.get("url", ""),
            "image": data.get("image", ""),
            "category": classify_category(data.get("name", "")),
        }
    except Exception:
        return None


def extract_embedded_json(page):
    """script 태그 내 JSON 데이터에서 제품 정보를 추출합니다."""
    products = []
    try:
        scripts = page.query_selector_all("script:not([src])")
        for script in scripts:
            text = script.inner_text()
            if not ("product" in text.lower() and "price" in text.lower()):
                continue
            # window.__NEXT_DATA__, __INITIAL_STATE__ 등의 패턴 탐색
            for pattern in [
                r'window\.__NEXT_DATA__\s*=\s*({.+?});?\s*</script',
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});?\s*</script',
                r'__data\s*=\s*({.+?});?\s*</script',
            ]:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        products.extend(find_products_in_dict(data))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass
    return products


def find_products_in_dict(obj, depth=0):
    """중첩된 dict/list에서 상품 정보를 재귀적으로 찾습니다."""
    products = []
    if depth > 10:
        return products

    if isinstance(obj, dict):
        # 상품 객체로 보이는 경우
        has_name = any(k in obj for k in ("productName", "name", "title", "itemName"))
        has_price = any(k in obj for k in ("salePrice", "price", "salesPrice", "finalPrice"))
        if has_name and has_price:
            name = obj.get("productName") or obj.get("name") or obj.get("title") or obj.get("itemName", "")
            price = parse_price(str(
                obj.get("salePrice") or obj.get("salesPrice") or
                obj.get("finalPrice") or obj.get("price", 0)
            ))
            original = parse_price(str(
                obj.get("listPrice") or obj.get("originalPrice") or
                obj.get("basePrice") or obj.get("price", 0)
            ))
            url = obj.get("productUrl") or obj.get("url") or obj.get("landingUrl", "")
            image = obj.get("productImage") or obj.get("imageUrl") or obj.get("thumbnail", "")

            if name and price:
                if url and not url.startswith("http"):
                    url = f"https://www.coupang.com{url}"
                products.append({
                    "name": str(name),
                    "price": price,
                    "originalPrice": original if original > price else price,
                    "url": str(url),
                    "image": str(image),
                    "category": classify_category(str(name)),
                })
        else:
            for v in obj.values():
                products.extend(find_products_in_dict(v, depth + 1))

    elif isinstance(obj, list):
        for item in obj:
            products.extend(find_products_in_dict(item, depth + 1))

    return products


def extract_from_dom(page):
    """DOM 요소에서 제품 정보를 추출합니다."""
    products = []
    # 쿠팡에서 사용할 수 있는 다양한 셀렉터
    container_selectors = [
        ".product-card", ".product-item",
        "[class*='ProductCard']", "[class*='product-card']",
        "li.baby-product", ".baby-product-wrap",
        "[class*='ProductItem']",
        "a[data-product-id]", "[data-item-id]",
    ]

    for selector in container_selectors:
        items = page.query_selector_all(selector)
        if not items:
            continue
        print(f"    셀렉터 '{selector}'로 {len(items)}개 요소 발견")
        for item in items:
            p = parse_dom_element(item)
            if p:
                products.append(p)
        if products:
            break

    return products


def extract_search_results(page):
    """쿠팡 검색 결과 페이지에서 제품을 추출합니다."""
    products = []

    # 검색 결과 상품 컨테이너
    selectors = [
        "li.search-product",
        "li.baby-product",
        ".search-product",
    ]

    for selector in selectors:
        items = page.query_selector_all(selector)
        if not items:
            continue
        for item in items:
            p = parse_dom_element(item)
            if p:
                products.append(p)
        if products:
            break

    return products


def parse_dom_element(el):
    """DOM 요소에서 이름, 가격, URL, 이미지를 추출합니다."""
    try:
        # 이름
        name = ""
        for sel in [".name", ".product-name", ".title", "a[title]"]:
            node = el.query_selector(sel)
            if node:
                name = (node.get_attribute("title") or node.inner_text()).strip()
                if name:
                    break
        if not name:
            img = el.query_selector("img[alt]")
            if img:
                name = (img.get_attribute("alt") or "").strip()
        if not name:
            return None

        # 현재 가격
        price = 0
        for sel in [".price-value", ".sale-price", "strong.price-value", "[class*='price']"]:
            node = el.query_selector(sel)
            if node:
                price = parse_price(node.inner_text())
                if price:
                    break

        # 원래 가격
        original_price = 0
        for sel in [".origin-price", ".base-price", "del", "s"]:
            node = el.query_selector(sel)
            if node:
                original_price = parse_price(node.inner_text())
                if original_price:
                    break

        if not price:
            return None
        if not original_price or original_price < price:
            original_price = price

        # URL
        url = ""
        link = el.query_selector("a[href]")
        if link:
            url = link.get_attribute("href") or ""
            if url.startswith("/"):
                url = f"https://www.coupang.com{url}"

        # 이미지
        image = ""
        img_el = el.query_selector("img")
        if img_el:
            image = (
                img_el.get_attribute("src")
                or img_el.get_attribute("data-img-src")
                or img_el.get_attribute("data-src")
                or ""
            )

        return {
            "name": name,
            "price": price,
            "originalPrice": original_price,
            "url": url,
            "image": image,
            "category": classify_category(name),
        }
    except Exception:
        return None


def deduplicate(products):
    """중복 상품을 제거합니다."""
    seen = set()
    unique = []
    for p in products:
        key = re.sub(r"\s+", "", p["name"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def add_discount_info(products):
    """할인율과 절약 금액을 계산합니다."""
    for p in products:
        orig = p.get("originalPrice", 0)
        curr = p.get("price", 0)
        if orig > curr > 0:
            p["discountPercent"] = round((1 - curr / orig) * 100, 1)
            p["savings"] = orig - curr
        else:
            p["discountPercent"] = 0
            p["savings"] = 0
    products.sort(key=lambda x: x["discountPercent"], reverse=True)
    return products


def save_results(products):
    """결과를 JSON 파일로 저장합니다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "lastUpdated": datetime.now(KST).isoformat(),
        "totalProducts": len(products),
        "sourceUrl": BRAND_SHOP_URL,
        "products": products,
    }
    OUTPUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[저장] {len(products)}개 상품 -> {OUTPUT_FILE}")


def main():
    print("=" * 60)
    print(" 쿠팡 애플 브랜드샵 가격 모니터링")
    print(f" {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}")
    print("=" * 60)

    all_products = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="ko-KR",
            )
            # 자동화 탐지 회피
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            page = context.new_page()

            # 전략 1: 브랜드샵 직접 접근
            products = try_brand_shop(page)
            all_products.extend(products)

            # 전략 2: 브랜드샵 실패 시 검색 사용
            if not all_products:
                products = try_search(page)
                all_products.extend(products)

            browser.close()

    except Exception as e:
        print(f"\n[ERROR] 스크래핑 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 후처리
    all_products = deduplicate(all_products)
    all_products = [p for p in all_products if is_apple_product(p["name"])]
    all_products = add_discount_info(all_products)

    save_results(all_products)

    # 결과 요약
    if all_products:
        deals = [p for p in all_products if p["discountPercent"] > 0]
        print(f"\n총 {len(all_products)}개 상품, 그 중 {len(deals)}개 할인 중")
        if deals:
            print("\n할인율 TOP 10:")
            print("-" * 50)
            for i, p in enumerate(deals[:10], 1):
                print(f" {i:2d}. {p['name'][:45]}")
                print(f"     {p['originalPrice']:>10,}원 -> {p['price']:>10,}원"
                      f"  ({p['discountPercent']}% 할인)")
    else:
        print("\n[WARN] 수집된 상품이 없습니다.")
        print("       쿠팡이 자동 접근을 차단했을 수 있습니다.")
        print("       쿠팡 파트너스 API 사용을 권장합니다.")

    print(f"\n완료: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}")


if __name__ == "__main__":
    main()
