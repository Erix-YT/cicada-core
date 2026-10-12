#!/usr/bin/env python3
"""
Cicada core builder — готовит ядра для плагина Cicada: sing-box-lx (AmneziaWG + XHTTP + Hysteria2 + TUIC + ...) и Xray (AndroidLibXrayLite).
Выбор ядра: --core singbox (по умолчанию) или --core xray; --latest берёт свежий релиз апстрима.

Что делает:
  1. скачивает libbox-1.14.0-lx.35.aar с GitHub (Leadaxe/sing-box-lx) и сверяет SHA-256 с релизом;
  2. достаёт из него arm64-v8a/libbox.so и Java-классы;
  3. превращает Java-классы в classes.dex (d8 берётся из Android SDK или скачивается автоматически; нужна Java);
  4. сжимает libbox.so в .gz и считает хэши;
  5. выгружает список публичных классов/методов libbox (api.txt) — по нему пишется обвязка в плагине;
  6. складывает всё в папку cicada-core/ и печатает JSON с хэшами.

Запуск (Windows / macOS / Linux, нужен Python 3.8+ и Java 11+):
    python build_core.py
Если d8 не находится сам:
    python build_core.py --d8 "C:\\Users\\you\\AppData\\Local\\Android\\Sdk\\build-tools\\34.0.0\\d8.bat"
Без Android SDK скрипт сам скачает D8 (нужна только Java 17).
Уже скачан AAR:
    python build_core.py --aar путь\\к\\libbox-1.14.0-lx.35.aar --skip-hash
"""
import argparse
import glob
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

VERSION = "1.14.0-lx.35"
AAR_URL = "https://github.com/Leadaxe/sing-box-lx/releases/download/v%s/libbox-%s.aar" % (VERSION, VERSION)
AAR_SHA256 = "c4bc5f7b6aea3b022fff83421baeacbf672298cd167d828a6484cdbb1e896281"
OUT = "cicada-core"
R8_VERSION = "8.5.35"  # D8 из Google Maven; ставить Android SDK не нужно, нужна только Java (JDK 17)
R8_URLS = ["https://dl.google.com/dl/android/maven2/com/android/tools/r8/%s/r8-%s.jar" % (R8_VERSION, R8_VERSION),
           "https://maven.google.com/com/android/tools/r8/%s/r8-%s.jar" % (R8_VERSION, R8_VERSION)]


CORES = {
    "singbox": {"upstream": "Leadaxe/sing-box-lx", "asset_prefix": "libbox-", "so": "libbox.so",
                "api_prefix": "io.nekohasekai.libbox.", "title": "sing-box-lx", "out": "cicada-core"},
    "xray": {"upstream": "2dust/AndroidLibXrayLite", "asset_prefix": "", "so": "libgojni.so",
             "api_prefix": "libv2ray.", "title": "Xray (AndroidLibXrayLite)", "out": "cicada-core-xray"},
}
CORE = "singbox"
UPSTREAM = CORES[CORE]["upstream"]


def api_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "cicada-core-builder"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def resolve_latest():
    """Последний релиз апстрима выбранного ядра; SHA-256 AAR берётся из метаданных GitHub (поле digest)."""
    global VERSION, AAR_URL, AAR_SHA256
    c = CORES[CORE]
    rel = api_json("https://api.github.com/repos/%s/releases/latest" % c["upstream"])
    assets = [a for a in rel.get("assets", []) if a["name"].startswith(c["asset_prefix"]) and a["name"].endswith(".aar")]
    if not assets:
        sys.exit("В последнем релизе %s нет .aar (тег %s)." % (c["upstream"], rel.get("tag_name")))
    a = assets[0]
    digest = (a.get("digest") or "")
    if not digest.startswith("sha256:") or len(digest) != 71:
        sys.exit("GitHub не отдал SHA-256 для %s — без хэша не собираю." % a["name"])
    VERSION = rel["tag_name"].lstrip("v")
    AAR_URL = a["browser_download_url"]
    AAR_SHA256 = digest[7:]


def set_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write("%s=%s\n" % (k, v))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dst):
    print("Скачиваю %s" % url)

    def hook(blocks, bs, total):
        if total > 0:
            done = min(100, blocks * bs * 100 // total)
            sys.stdout.write("\r  %d%%" % done)
            sys.stdout.flush()

    urllib.request.urlretrieve(url, dst, hook)
    print()


def find_d8(explicit):
    if explicit:
        return explicit
    names = ("d8.bat", "d8") if os.name == "nt" else ("d8",)
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    roots = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
             os.path.expanduser("~/Android/Sdk"), os.path.expanduser("~/Library/Android/sdk"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")]
    for r in roots:
        if not r:
            continue
        for n in names:
            found = sorted(glob.glob(os.path.join(r, "build-tools", "*", n)))
            if found:
                return found[-1]
    return None


def java_major(java_path):
    """Главная версия Java по `java -version` (8, 11, 17, ...). None, если не удалось определить."""
    try:
        r = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    import re
    m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
    if not m:
        return None
    major = int(m.group(1))
    return int(m.group(2) or 0) if major == 1 else major  # "1.8.0" -> 8


def find_java(explicit=None, minimum=11):
    """Ищет java версии >= minimum: --java, JAVA_HOME, стандартные папки JDK, и только потом PATH."""
    if explicit:
        if not os.path.exists(explicit):
            sys.exit("Файл --java не найден: %s" % explicit)
        v = java_major(explicit)
        if v is not None and v < minimum:
            sys.exit("--java указывает на Java %s, а нужна %d+." % (v, minimum))
        return explicit
    exe = "java" + (".exe" if os.name == "nt" else "")
    cands = []
    jh = os.environ.get("JAVA_HOME")
    if jh:
        cands.append(os.path.join(jh, "bin", exe))
    pats = []
    if os.name == "nt":
        for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            for vendor in ("Java", "Eclipse Adoptium", "Microsoft", "Zulu", "BellSoft", "Amazon Corretto", "Semeru", "JetBrains"):
                pats.append(os.path.join(pf, vendor, "*", "bin", exe))
        pats.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Eclipse Adoptium", "*", "bin", exe))
        pats.append(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Android", "Android Studio", "jbr", "bin", exe))
        pats.append(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "JetBrains", "*", "jbr", "bin", exe))
    elif sys.platform == "darwin":
        pats.append("/Library/Java/JavaVirtualMachines/*/Contents/Home/bin/" + exe)
    else:
        pats.append("/usr/lib/jvm/*/bin/" + exe)
    for pat in pats:
        cands += sorted(glob.glob(pat), reverse=True)
    p = shutil.which("java")
    if p:
        cands.append(p)
    best, best_v, seen = None, 0, set()
    for c in cands:
        if not c or c in seen or not os.path.exists(c):
            continue
        seen.add(c)
        v = java_major(c)
        if v and v >= minimum and v > best_v:
            best, best_v = c, v
    if best:
        print("Java %d: %s" % (best_v, best))
    return best


def find_java_tool(name):
    """java / javap: PATH, JAVA_HOME, затем стандартные папки JDK (Windows/macOS/Linux)."""
    exe = name + (".exe" if os.name == "nt" else "")
    p = shutil.which(name)
    if p:
        return p
    cands = []
    jh = os.environ.get("JAVA_HOME")
    if jh:
        cands.append(os.path.join(jh, "bin", exe))
    pats = []
    if os.name == "nt":
        for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            for vendor in ("Java", "Eclipse Adoptium", "Microsoft", "Zulu", "BellSoft", "Amazon Corretto", "Semeru"):
                pats.append(os.path.join(pf, vendor, "*", "bin", exe))
        pats.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Eclipse Adoptium", "*", "bin", exe))
        pats.append(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Android", "Android Studio", "jbr", "bin", exe))
    elif sys.platform == "darwin":
        pats.append("/Library/Java/JavaVirtualMachines/*/Contents/Home/bin/" + exe)
    else:
        pats.append("/usr/lib/jvm/*/bin/" + exe)
    for pat in pats:
        cands += sorted(glob.glob(pat), reverse=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def find_local_r8(explicit):
    """r8.jar, скачанный вручную: --r8, затем r8*.jar рядом со скриптом / в cicada-core/_tools / в Загрузках."""
    if explicit:
        if not os.path.exists(explicit):
            sys.exit("Файл --r8 не найден: %s" % explicit)
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = [os.getcwd(), here, os.path.join(OUT, "_tools"), os.path.expanduser("~/Downloads")]
    found = []
    for d in dirs:
        found += glob.glob(os.path.join(d, "r8*.jar"))
    found = [f for f in found if os.path.getsize(f) > 1000000]  # настоящий r8 — несколько МБ
    return sorted(found, key=os.path.getmtime)[-1] if found else None


def r8_command(explicit=None, java_explicit=None):
    """Нет d8 из SDK — берём r8.jar (скачанный вручную или от Google) и запускаем D8 через Java 11+."""
    java = find_java(java_explicit)
    if not java:
        sys.exit("Не найдена Java 11+ (искал в JAVA_HOME, стандартных папках и PATH; Java 8 не подходит, D8 требует 11+). "
                 "Поставьте JDK 17 (https://adoptium.net -> Temurin 17) или укажите путь явно: "
                 "python build_core.py --java \"C:\\Program Files\\Java\\jdk-17\\bin\\java.exe\"")
    tools = os.path.join(OUT, "_tools")
    os.makedirs(tools, exist_ok=True)
    jar = find_local_r8(explicit) or os.path.join(tools, "r8-%s.jar" % R8_VERSION)
    if os.path.exists(jar):
        print("r8.jar: %s" % jar)
    if not os.path.exists(jar):
        last = None
        for url in R8_URLS:
            try:
                download(url, jar)
                try:  # Google Maven отдаёт .sha256 рядом — сверяем, если есть
                    want = urllib.request.urlopen(url + ".sha256", timeout=20).read().decode().split()[0].strip()
                    if len(want) == 64 and want != sha256_file(jar):
                        os.remove(jar)
                        sys.exit("Хэш r8.jar не совпал — файл удалён, запустите ещё раз.")
                    print("Хэш r8.jar: совпал" if len(want) == 64 else "Хэш r8.jar: не проверен")
                except SystemExit:
                    raise
                except Exception:
                    print("Хэш r8.jar: не проверен (сервер не отдал .sha256)")
                break
            except SystemExit:
                raise
            except Exception as e:
                last = e
                if os.path.exists(jar):
                    os.remove(jar)
        else:
            sys.exit("Не удалось скачать r8.jar (%s).\nСкачайте его вручную и положите рядом со скриптом "
                     "(имя r8*.jar) или укажите: python build_core.py --r8 путь\\r8.jar" % last)
    return [java, "-cp", jar, "com.android.tools.r8.D8"]


def find_android_jar():
    for r in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
              os.path.expanduser("~/Android/Sdk"), os.path.expanduser("~/Library/Android/sdk"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")):
        if r:
            found = sorted(glob.glob(os.path.join(r, "platforms", "android-*", "android.jar")))
            if found:
                return found[-1]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", choices=sorted(CORES), default="singbox", help="какое ядро собирать (по умолчанию singbox)")
    ap.add_argument("--aar", help="путь к уже скачанному AAR")
    ap.add_argument("--d8", help="путь к d8 (Android SDK build-tools)")
    ap.add_argument("--java", help="путь к java.exe версии 11+ (например C:\\Program Files\\Java\\jdk-17\\bin\\java.exe)")
    ap.add_argument("--r8", help="путь к r8.jar / r8lib.jar, скачанному вручную (содержит D8)")
    ap.add_argument("--latest", action="store_true", help="взять последний релиз sing-box-lx (версия и хэш берутся с GitHub)")
    ap.add_argument("--resolve-only", action="store_true", help="только определить версию (с --latest) и выйти")
    ap.add_argument("--repo", help="owner/name вашего репозитория: в core.json попадут готовые ссылки на релиз core-<версия>")
    ap.add_argument("--skip-hash", action="store_true", help="не сверять хэш AAR (только для своего файла)")
    args = ap.parse_args()

    global CORE, OUT
    CORE = args.core
    OUT = CORES[CORE]["out"]
    if CORE != "singbox" and not args.latest and not args.aar:
        sys.exit("Для ядра %s укажите --latest или --aar." % CORE)
    if args.latest:
        resolve_latest()
        print("Последняя версия: %s" % VERSION)
        set_output(version=VERSION, tag="%s-%s" % (CORE, VERSION))
        if args.resolve_only:
            return

    os.makedirs(OUT, exist_ok=True)
    work = os.path.join(OUT, "_work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)

    aar = args.aar or os.path.join(work, "libbox.aar")
    if not args.aar:
        download(AAR_URL, aar)
    got = sha256_file(aar)
    if got != AAR_SHA256 and not args.skip_hash:
        sys.exit("ХЭШ AAR НЕ СОВПАЛ!\n  ожидался %s\n  получен  %s\nНе используйте этот файл." % (AAR_SHA256, got))
    print("Хэш AAR: %s" % ("совпал" if got == AAR_SHA256 else "НЕ проверен (%s)" % got))

    jars, so_path = [], None
    with zipfile.ZipFile(aar) as z:
        names = z.namelist()
        print("Содержимое AAR (jni/ и jar):")
        for n in names:
            if n.startswith("jni/") or n.endswith(".jar"):
                print("  ", n)
        want_so = "jni/arm64-v8a/" + CORES[CORE]["so"]
        if want_so not in names:
            cand = [n for n in names if n.startswith("jni/arm64-v8a/") and n.endswith(".so")]
            if not cand:
                sys.exit("В AAR нет arm64-v8a .so — этот файл не подходит.")
            want_so = cand[0]
        so_path = os.path.join(work, os.path.basename(want_so))
        with z.open(want_so) as src, open(so_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        for n in names:
            if n == "classes.jar" or (n.startswith("libs/") and n.endswith(".jar")):
                p = os.path.join(work, n.replace("/", "_"))
                with z.open(n) as src, open(p, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                jars.append(p)
    if not jars:
        sys.exit("В AAR нет classes.jar.")

    # --- dex
    d8 = find_d8(args.d8)
    base = [d8] if d8 else r8_command(args.r8, args.java)
    print("d8:", " ".join(base))
    dex_dir = os.path.join(work, "dex")
    aj = find_android_jar()
    r = None
    for extra_flags in ([], ["--no-desugaring"]):  # второй заход — если desugaring без android.jar не прошёл
        shutil.rmtree(dex_dir, ignore_errors=True)
        os.makedirs(dex_dir)
        cmd = base + ["--release", "--min-api", "21", "--output", dex_dir] + extra_flags
        if aj:
            cmd += ["--lib", aj]
        cmd += jars
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and glob.glob(os.path.join(dex_dir, "*.dex")):
            break
        print("d8 не справился%s, пробую иначе…" % (" (с desugaring)" if not extra_flags else ""))
    if r.returncode != 0:
        sys.exit("d8 завершился с ошибкой:\n%s\n%s" % (r.stdout, r.stderr))
    dexes = sorted(glob.glob(os.path.join(dex_dir, "*.dex")))
    if not dexes:
        sys.exit("d8 не создал dex.")
    if len(dexes) > 1:
        print("ВНИМАНИЕ: получилось %d dex-файлов (%s). Плагин ждёт один — пришлите их все." % (len(dexes), ", ".join(map(os.path.basename, dexes))))
    shutil.copy(dexes[0], os.path.join(OUT, "classes.dex"))
    for extra in dexes[1:]:
        shutil.copy(extra, os.path.join(OUT, os.path.basename(extra)))

    # --- so + gz
    so_out = os.path.join(OUT, CORES[CORE]["so"])
    shutil.copy(so_path, so_out)
    gz_out = so_out + ".gz"
    with open(so_out, "rb") as src, gzip.open(gz_out, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)

    # --- API dump
    api_txt = os.path.join(OUT, "api.txt")
    with open(api_txt, "w", encoding="utf-8") as f:
        javap = find_java_tool("javap")
        for jar in jars:
            with zipfile.ZipFile(jar) as z:
                classes = sorted(n[:-6].replace("/", ".") for n in z.namelist()
                                 if n.endswith(".class") and "$" not in n and not n.startswith("META-INF"))
            f.write("== %s: %d классов ==\n" % (os.path.basename(jar), len(classes)))
            f.write("\n".join(classes) + "\n\n")
            if javap:
                sel = [c for c in classes if c.startswith(CORES[CORE]["api_prefix"])]
                if sel:
                    out = subprocess.run([javap, "-public", "-cp", jar] + sel, capture_output=True, text=True)
                    f.write(out.stdout + "\n")
            else:
                f.write("(javap не найден — поставьте JDK, чтобы в файл попали сигнатуры методов)\n")

    base = ("https://github.com/%s/releases/download/%s-%s/" % (args.repo, CORE, VERSION)) if args.repo else None
    info = {
        "name": "%s %s" % (CORES[CORE]["title"], VERSION),
        "core": CORE,
        "version": VERSION,
        "dex": (base + "classes.dex") if base else "<ссылка на classes.dex>",
        "dex_sha256": sha256_file(os.path.join(OUT, "classes.dex")),
        "so": (base + CORES[CORE]["so"] + ".gz") if base else "<ссылка на %s.gz>" % CORES[CORE]["so"],
        "so_sha256": sha256_file(gz_out),
        "so_raw_sha256": sha256_file(so_out),
        "aar_sha256": got,
        "source": AAR_URL,
    }
    with open(os.path.join(OUT, "core.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    shutil.rmtree(work, ignore_errors=True)

    print("\nГотово. Папка: %s/" % OUT)
    for n in sorted(os.listdir(OUT)):
        print("  %-18s %8.1f МБ" % (n, os.path.getsize(os.path.join(OUT, n)) / 1048576.0))
    print("\n%s" % json.dumps(info, indent=2, ensure_ascii=False))
    print("\nДальше: загрузите classes.dex и libbox.so.gz в релиз на GitHub (или свой канал) и пришлите мне"
          "\nссылки + файлы core.json и api.txt.")


if __name__ == "__main__":
    main()
