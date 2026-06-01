"""下载中文字体供 PDF 生成使用"""
import os
import sys
from pathlib import Path

FONT_DIR = Path(__file__).parent

FONT_SOURCES = {
    "NotoSansSC-Regular.ttf": [
        # jsDelivr npm CDN（国内 CDN 节点，速度快）
        "https://cdn.jsdelivr.net/npm/noto-sans-sc@37.0.0/noto_sans_sc_regular.ttf",
        # 阿里云镜像站（ECS 内网访问极快）
        "https://mirrors.aliyun.com/github/releases/googlefonts/noto-cjk/Sans2.004/18_NotoSansSC.zip",
        # GitHub 原始地址（部分国内服务器可访问）
        "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf",
    ],
}

def download_file(url: str, target: Path) -> bool:
    """下载文件，支持 requests 和 urllib 两种方式"""
    try:
        import requests
        print(f"  正在下载（requests）...")
        r = requests.get(url, timeout=120, allow_redirects=True)
        r.raise_for_status()
        target.write_bytes(r.content)
        return True
    except ImportError:
        pass
    except Exception as e:
        print(f"  requests 方式失败: {e}")

    try:
        import urllib.request
        print(f"  正在下载（urllib）...")
        urllib.request.urlretrieve(url, target)
        return True
    except Exception as e:
        print(f"  urllib 方式失败: {e}")

    return False


def ensure_font(filename: str, urls: list[str]) -> bool:
    """确保字体文件存在，不存在则下载"""
    target = FONT_DIR / filename
    if target.exists() and target.stat().st_size > 1000:
        print(f"  ✓ {filename} 已存在 ({target.stat().st_size // 1024} KB)")
        return True

    print(f"  ↓ 下载 {filename}...")
    for url in urls:
        if download_file(url, target):
            size = target.stat().st_size
            print(f"  ✓ {filename} 下载完成 ({size // 1024} KB)")
            return True

        # 如果下载失败且是 ZIP 链接，尝试下载后解压
        if ".zip" in url:
            import zipfile
            zip_tmp = FONT_DIR / "_tmp_font.zip"
            if download_file(url, zip_tmp):
                try:
                    with zipfile.ZipFile(zip_tmp) as zf:
                        for name in zf.namelist():
                            if name.lower().endswith((".ttf", ".otf")) and not name.startswith("__"):
                                with zf.open(name) as src, open(target, "wb") as dst:
                                    dst.write(src.read())
                                size = target.stat().st_size
                                print(f"  ✓ {filename} 从 ZIP 解压完成 ({size // 1024} KB)")
                                zip_tmp.unlink()
                                return True
                except Exception as e:
                    print(f"  ZIP 解压失败: {e}")
                finally:
                    if zip_tmp.exists():
                        zip_tmp.unlink()

    print(f"  ✗ {filename} 下载失败")
    return False


if __name__ == "__main__":
    print("=" * 50)
    print("  PDF 中文字体下载工具")
    print("=" * 50)

    success = all(
        ensure_font(name, urls)
        for name, urls in FONT_SOURCES.items()
    )

    if success:
        print("\n✅ 全部字体就绪，PDF 生成将自动使用此字体")
    else:
        print("\n⚠️  部分字体下载失败，可尝试通过系统包管理器安装：")
        print("   Ubuntu/Debian:  sudo apt install fonts-wqy-microhei")
        print("   CentOS/RHEL:    sudo yum install wqy-microhei-fonts")
        print("   Fedora:         sudo dnf install google-noto-sans-cjk-fonts")
        sys.exit(1)
