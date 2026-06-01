"""
URL 内容抓取与正文抽取模块 — 将外部网页内容导入知识库。

技术栈:
  - requests + BeautifulSoup: 快速抓取静态页面
  - readability-lxml: 智能正文提取（类似 Safari 阅读模式）
  - Playwright 无头 Chromium: 渲染 JS 动态页面（SPA）

抓取策略（多级降级）:
  1. requests 快速抓取 HTML → readability-lxml 提取正文
  2. 内容质量检测 → 低质量时触发 Playwright 浏览器渲染
  3. Playwright 在浏览器内执行 JS 提取正文（智能选择器）

URL 安全校验:
  - 仅允许 http/https 协议
  - 禁止内网 IP（127.x, 10.x, 192.168.x, 172.16-31.x）
  - 禁止 localhost
  - 支持域名白名单

支持: http/https 静态页面、JS SPA（通过 Playwright 渲染）
不支持: 需登录页面、内网地址
"""

import re
import ipaddress
from urllib.parse import urlparse
from typing import Optional, Tuple, List

import requests
from bs4 import BeautifulSoup

# 尝试导入 readability，不可用时降级到 BeautifulSoup
try:
    from readability import Document as ReadabilityDocument
    HAS_READABILITY = True
except ImportError:
    HAS_READABILITY = False
    print("[URL加载] readability-lxml 未安装，将使用 BeautifulSoup 降级模式")

# 尝试导入 playwright，不可用时禁用浏览器渲染
try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    print("[URL加载] playwright 未安装，动态页面渲染功能不可用")

# Playwright 浏览器是否已安装标记
_BROWSER_INSTALLED = None


async def _ensure_browser_installed():
    """检查并自动安装 Playwright Chromium 浏览器内核"""
    global _BROWSER_INSTALLED
    if _BROWSER_INSTALLED is True:
        return True
    if not HAS_PLAYWRIGHT:
        print("[URL加载] playwright 包未安装，跳过浏览器渲染")
        return False

    import subprocess, sys

    async def _try_launch():
        """尝试启动浏览器验证是否可用"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            await browser.close()
        return True

    # 第一步: 直接尝试启动
    try:
        await _try_launch()
        _BROWSER_INSTALLED = True
        print("[URL加载] Chromium 浏览器已就绪")
        return True
    except Exception as e:
        print(f"[URL加载] Chromium 启动失败: {e}")

    # 第二步: 安装浏览器内核
    print("[URL加载] 正在自动下载安装 Chromium...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True, timeout=300, capture_output=True, text=True
        )
        print("[URL加载] Chromium 浏览器下载完成")
    except Exception as e:
        print(f"[URL加载] Chromium 下载失败: {e}")
        _BROWSER_INSTALLED = False
        return False

    # 第三步: 尝试安装系统依赖（Linux 下需要）
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install-deps", "chromium"],
            check=True, timeout=300, capture_output=True, text=True
        )
        print("[URL加载] 系统依赖安装完成")
    except Exception as e:
        print(f"[URL加载] 系统依赖安装失败(可能需要sudo): {e}")

    # 第四步: 重新验证是否可用
    try:
        await _try_launch()
        _BROWSER_INSTALLED = True
        print("[URL加载] Chromium 安装并验证成功")
        return True
    except Exception as e:
        print(f"[URL加载] Chromium 安装后仍无法启动: {e}")
        print("[URL加载] 请手动执行: playwright install chromium")
        _BROWSER_INSTALLED = False
        return False

# Playwright 渲染正文的最小长度阈值（低于此值直接触发浏览器渲染）
MIN_CONTENT_LENGTH = 100


def _is_low_quality_content(html: str, content: str) -> bool:
    """
    检测提取的内容是否为低质量（菜单/导航残留而非真正文章）。
    用于决定是否需要触发 Playwright 渲染。

    返回 True 表示内容质量低，应触发浏览器渲染。
    """
    # 内容太短，直接触发
    if len(content.strip()) < MIN_CONTENT_LENGTH:
        return True

    lines = [l for l in content.strip().splitlines() if l.strip()]
    if not lines:
        return True

    # 指标1: 平均行长度太短（菜单项通常是短文本）
    avg_line_len = sum(len(l.strip()) for l in lines) / len(lines)

    # 指标2: 长行占比（真正文章会有较多长句子/段落）
    long_lines = [l for l in lines if len(l.strip()) > 30]
    long_ratio = len(long_lines) / len(lines)

    # 指标3: HTML 中是否有 SPA 框架标记（空壳页面特征）
    html_lower = html.lower()
    has_spa_marker = any(marker in html_lower for marker in [
        'id="app"', 'id="root"', 'id="__next"',
        'id="__nuxt"', 'data-reactroot', 'id="__vue'
    ])

    # 指标4: HTML 中 <p> 标签极少（正常文章会有段落）
    p_count = html_lower.count('<p')

    # 综合判断
    # 情况A: SPA 空壳 + 内容像菜单
    if has_spa_marker and avg_line_len < 20 and p_count < 10:
        print(f"[URL加载] 检测到 SPA 空壳页面(平均行长{avg_line_len:.0f}, p标签{p_count}个)")
        return True

    # 情况B: 内容大部分是短行（菜单特征）
    if avg_line_len < 15 and long_ratio < 0.2 and len(lines) > 5:
        print(f"[URL加载] 检测到菜单特征内容(平均行长{avg_line_len:.0f}, 长行比{long_ratio:.0%})")
        return True

    # 情况C: SPA 框架 + 没有实质段落 + 内容不够长
    if has_spa_marker and p_count < 5 and len(content.strip()) < 500:
        print(f"[URL加载] SPA 页面内容不足(p标签{p_count}个, 内容{len(content.strip())}字)")
        return True

    return False

# 请求超时（秒）
REQUEST_TIMEOUT = 30

# 请求重试次数
REQUEST_RETRIES = 2

# 重试间隔（秒）
RETRY_DELAY = 2

# 模拟浏览器请求头
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def validate_url(url: str, allowed_domains: Optional[List[str]] = None) -> Tuple[bool, str]:
    """
    校验 URL 合法性。

    规则：
    - 仅允许 http / https
    - 禁止内网 IP（127.x / 10.x / 192.168.x / 172.16-31.x）
    - 可选域名白名单

    返回 (is_valid, error_message)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL 格式无效"

    # 协议校验
    if parsed.scheme not in ("http", "https"):
        return False, "仅支持 http/https 协议"

    hostname = parsed.hostname
    if not hostname:
        return False, "无效的 URL 格式（缺少域名）"

    # localhost 快速拦截
    if hostname.lower() in ("localhost",):
        return False, "禁止访问本地地址"

    # IP 内网检测
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f"禁止访问内网/保留地址: {hostname}"
    except ValueError:
        pass  # 不是 IP，是域名，继续

    # 域名白名单（可选）
    if allowed_domains:
        if not any(hostname == d or hostname.endswith(f".{d}") for d in allowed_domains):
            return False, f"域名不在白名单内: {hostname}"

    return True, ""


def fetch_url(url: str) -> Tuple[str, str]:
    """
    抓取 URL 页面 HTML。
    返回 (html_text, final_url)，失败时抛出异常。
    支持自动重试，应对慢速或不稳定站点。
    """
    import time
    
    last_exception = None
    for attempt in range(1 + REQUEST_RETRIES):
        try:
            response = requests.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()

            # 优先使用响应头中的编码，fallback 到 apparent_encoding
            encoding = response.encoding or response.apparent_encoding or "utf-8"
            try:
                html = response.content.decode(encoding, errors="replace")
            except (LookupError, UnicodeDecodeError):
                html = response.text

            return html, str(response.url)
        except Exception as e:
            last_exception = e
            if attempt < REQUEST_RETRIES:
                print(f"[URL加载] 请求失败(第{attempt + 1}次): {type(e).__name__}: {e}，{RETRY_DELAY}s后重试...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"[URL加载] 请求失败(已重试{REQUEST_RETRIES}次): {type(e).__name__}: {e}")
                raise


async def fetch_url_with_browser(url: str, wait_seconds: float = 3) -> Tuple[str, str]:
    """
    使用 Playwright 无头浏览器渲染页面后获取 HTML。
    适用于 JavaScript 动态渲染的 SPA 页面。
    返回 (html_text, final_url)
    """
    if not HAS_PLAYWRIGHT or not await _ensure_browser_installed():
        raise RuntimeError("Playwright 未安装或浏览器内核不可用")

    print(f"[URL加载] 启动浏览器渲染: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        try:
            page = await browser.new_page()
            await page.set_extra_http_headers({
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
            })
            # 导航并等待网络空闲（页面加载完成）
            await page.goto(url, wait_until="networkidle", timeout=25000)
            # 额外等待确保动态内容渲染完毕
            await page.wait_for_timeout(int(wait_seconds * 1000))
            html = await page.content()
            final_url = page.url
        finally:
            await browser.close()

    print(f"[URL加载] 浏览器渲染完成，HTML 长度: {len(html)}")
    return html, final_url


async def extract_with_browser(url: str, wait_seconds: float = 5) -> Tuple[str, str, str]:
    """
    使用 Playwright 渲染页面并直接在浏览器内提取正文。
    通过 JS 尝试多个常见内容选择器，拾取文档主体文本。
    返回 (title, content, final_url)
    """
    if not HAS_PLAYWRIGHT or not await _ensure_browser_installed():
        raise RuntimeError("Playwright 未安装或浏览器内核不可用")

    print(f"[URL加载] 启动浏览器智能提取: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        try:
            page = await browser.new_page()
            await page.set_extra_http_headers({
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
            })
            await page.goto(url, wait_until="networkidle", timeout=25000)
            await page.wait_for_timeout(int(wait_seconds * 1000))

            # 在浏览器中执行 JS 提取正文
            result = await page.evaluate("""
            () => {
                // 获取标题
                let title = document.title || '';
                const h1 = document.querySelector('h1');
                if (h1) title = h1.innerText || title;

                // 常见文档站内容选择器（按优先级排序）
                const selectors = [
                    // 火山引擎文档
                    '.volc-doceditor-container',
                    '.zone-container.editor-kit-container',
                    // 通用文档站
                    'article',
                    '[role="main"]',
                    'main',
                    '.markdown-body',
                    '.doc-content',
                    '.content-body',
                    '.article-content',
                    '.post-content',
                    '.entry-content',
                    '.documentation-content',
                    '.page-content',
                    '.rich-text',
                    '#content',
                    '#main-content',
                    '.content',
                    // 腐竹、语雀等国内文档站
                    '.lake-engine-view',
                    '.ne-viewer-body',
                ];

                let text = '';
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const t = el.innerText || '';
                        if (t.length > text.length) {
                            text = t;
                        }
                    }
                }

                // 如果选择器都没找到足够内容，取 body
                if (text.length < 100) {
                    // 移除干扰元素
                    const removes = document.querySelectorAll(
                        'nav, header, footer, aside, script, style, iframe, .sidebar, .nav, .menu, .toc'
                    );
                    removes.forEach(el => el.remove());
                    text = (document.body && document.body.innerText) || '';
                }

                return { title, text };
            }
            """)

            title = result.get('title', '')
            content = result.get('text', '')
            final_url = page.url
        finally:
            await browser.close()

    print(f"[URL加载] 浏览器智能提取完成，标题: {title}，正文长度: {len(content)}")
    return title, content, final_url


def extract_content(html: str, url: str) -> Tuple[str, str]:
    """
    从 HTML 中提取标题和正文纯文本。
    返回 (title, clean_text)

    策略：
    1. readability-lxml 自动识别正文（首选）
    2. BeautifulSoup 移除干扰元素后提取 body 文本（降级）
    """
    title = ""
    text = ""

    # ── 第一优先：readability-lxml ──
    if HAS_READABILITY:
        try:
            doc = ReadabilityDocument(html)
            title = doc.title() or ""
            summary_html = doc.summary()
            soup = BeautifulSoup(summary_html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return _clean_title(title, url), _clean_text(text)
        except Exception as e:
            print(f"[URL加载] readability 提取失败，降级: {e}")

    # ── 降级：BeautifulSoup 手动提取 ──
    soup = BeautifulSoup(html, "html.parser")

    # 提取标题
    if not title:
        tag = soup.find("title")
        if tag:
            title = tag.get_text(strip=True)
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)

    # 移除常见干扰元素
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "iframe", "noscript", "form", "button"]):
        tag.decompose()

    body = soup.find("body") or soup
    text = body.get_text(separator="\n", strip=True)

    return _clean_title(title, url), _clean_text(text)


def _clean_title(title: str, fallback_url: str = "") -> str:
    """清洗标题，过长则截断"""
    t = re.sub(r"\s+", " ", title).strip()
    if not t:
        # 用 URL path 作为 fallback
        parsed = urlparse(fallback_url)
        t = (parsed.path.strip("/") or parsed.hostname or fallback_url)[:100]
    return t[:200]


def _clean_text(text: str) -> str:
    """
    清洗正文文本：
    - 合并连续空行（超过 2 行压缩为 1）
    - 去掉每行首尾空白
    - 过滤极短行（按钮文本/菜单残留）
    """
    # 合并连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    # 过滤长度 <= 1 的行（保留空行用于段落分隔）
    lines = [l for l in lines if len(l) != 1]
    return "\n".join(lines).strip()


async def load_url_document(url: str, allowed_domains: Optional[List[str]] = None) -> dict:
    """
    完整流程：校验 → 抓取 → 提取正文。
    当 requests 抓取结果正文过短时，自动降级到 Playwright 浏览器渲染。

    返回：
    {
        "filename": "<URL 字符串>",   # 用于 ChromaDB 增量更新的稳定 key
        "content":  "<正文文本>",
        "source_type": "url",
        "source_ref":  "<最终 URL>",
        "display_title": "<页面标题>"  # 仅用于展示
    }

    失败时抛出 ValueError / requests 异常。
    """
    # 1. 校验
    is_valid, err = validate_url(url, allowed_domains)
    if not is_valid:
        raise ValueError(f"URL 不合法: {err}")

    print(f"[URL加载] 开始抓取: {url}")

    # 2. 快速抓取（requests）
    html, final_url = fetch_url(url)
    print(f"[URL加载] 抓取成功，最终 URL: {final_url}，HTML 长度: {len(html)}")

    # 3. 提取正文
    title, content = extract_content(html, final_url)
    print(f"[URL加载] 提取完成，标题: {title}，正文长度: {len(content)}")

    # 4. 内容质量检测 → 低质量时触发 Playwright 浏览器智能提取
    is_low = _is_low_quality_content(html, content)
    print(f"[URL加载] 内容质量检测: {'低质量' if is_low else '正常'}, HAS_PLAYWRIGHT={HAS_PLAYWRIGHT}")

    if is_low and HAS_PLAYWRIGHT:
        print(f"[URL加载] 内容质量不佳，启用浏览器智能提取...")
        try:
            title_new, content_new, final_url = await extract_with_browser(url)
            content_new = _clean_text(content_new)
            title_new = _clean_title(title_new, final_url)
            print(f"[URL加载] 浏览器提取结果: 标题={title_new}, 正文长度={len(content_new)}, 前100字: {content_new[:100]}")
            if len(content_new.strip()) > len(content.strip()):
                title, content = title_new, content_new
                print(f"[URL加载] 浏览器智能提取成功，正文长度: {len(content)}")
            else:
                print(f"[URL加载] 浏览器提取未获得更多内容(原{len(content.strip())}字, 新{len(content_new.strip())}字)")
        except Exception as e:
            import traceback
            print(f"[URL加载] 浏览器提取失败: {e}")
            traceback.print_exc()
    elif is_low and not HAS_PLAYWRIGHT:
        print("[URL加载] 内容质量低但 Playwright 不可用，使用原始提取结果")

    if not content.strip():
        raise ValueError("页面正文内容为空，无法导入（可能需要登录或页面结构特殊）")

    return {
        "filename": final_url,        # 用 URL 本身作为 ChromaDB 稳定 key
        "content": content,
        "source_type": "url",
        "source_ref": final_url,
        "display_title": title,
    }
