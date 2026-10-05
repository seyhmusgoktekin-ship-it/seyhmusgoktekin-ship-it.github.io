#!/usr/bin/env python3
"""App Store ve Google Play'deki yayında uygulamaları bulup uygulamalar.json'u yeniler.

Uygulamalar içindeki "Diğer uygulamalarımız" ekranı bu dosyayı okur. Yeni bir
uygulama mağazaya çıkınca bir sonraki çalıştırmada listeye kendiliğinden girer.
AG Dekor uygulamaları (com.agdekor.*) listeye alınmaz.
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(KOK, "uygulamalar.json")
OZET = os.path.join(KOK, "araclar", "ozetler.json")

APPLE_GELISTIRICI = "6788586066"
PLAY_GELISTIRICI = "AG Dekor"
HARIC = ("com.agdekor.",)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


def getir(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def anahtar(kimlik):
    return kimlik.lower().replace("_", "")


def haric(kimlik):
    return any(kimlik.lower().startswith(h) for h in HARIC)


def ilk_cumle(metin, sinir=110):
    metin = " ".join(metin.split())
    m = re.match(r"(.+?[.!?])(\s|$)", metin)
    cumle = m.group(1) if m else metin
    if len(cumle) > sinir:
        cumle = cumle[: sinir - 1].rsplit(" ", 1)[0] + "…"
    return cumle


def meta(sayfa, ad):
    m = re.search(r'<meta[^>]+(?:property|name)="%s"[^>]*content="([^"]*)"' % re.escape(ad), sayfa)
    return html.unescape(m.group(1)).strip() if m else None


def apple(ulke):
    veri = json.loads(getir(
        f"https://itunes.apple.com/lookup?id={APPLE_GELISTIRICI}&entity=software&country={ulke}&limit=200"))
    sonuc = {}
    for s in veri.get("results", []):
        if s.get("wrapperType") != "software" or haric(s["bundleId"]):
            continue
        sonuc[anahtar(s["bundleId"])] = {
            "bundleId": s["bundleId"],
            "ad": s["trackName"],
            "aciklama": ilk_cumle(s.get("description", "")),
            "ikon": s.get("artworkUrl512") or s.get("artworkUrl100"),
            "url": f"https://apps.apple.com/app/id{s['trackId']}",
        }
    return sonuc


def play_paketleri():
    sayfa = getir("https://play.google.com/store/apps/developer?id="
                  + urllib.parse.quote_plus(PLAY_GELISTIRICI) + "&hl=tr&gl=TR")
    return sorted({p for p in re.findall(r"details\?id=([a-zA-Z0-9_.]+)", sayfa) if not haric(p)})


def play(paket, dil):
    sayfa = getir(f"https://play.google.com/store/apps/details?id={paket}&hl={dil}&gl=TR")
    ad = meta(sayfa, "og:title") or paket
    ad = re.sub(r"\s+-\s+(Google Play'de Uygulamalar|Apps on Google Play)$", "", ad)
    return {
        "paket": paket,
        "ad": ad,
        "aciklama": meta(sayfa, "og:description") or meta(sayfa, "description"),
        "ikon": re.sub(r"=s\d+.*$", "=s256", meta(sayfa, "og:image") or "") or None,
        "url": f"https://play.google.com/store/apps/details?id={paket}",
    }


def main():
    ozetler = json.load(open(OZET, encoding="utf-8")) if os.path.exists(OZET) else {}
    ios_tr, ios_en = apple("tr"), apple("us")
    paketler = play_paketleri()
    and_tr = {anahtar(p): play(p, "tr") for p in paketler}
    and_en = {anahtar(p): play(p, "en") for p in paketler}

    # Mağazalardan biri boş dönerse (engelleme/geçici hata) eski listeyi bozma.
    if not ios_tr or not paketler:
        print("Mağaza verisi eksik geldi (iOS: %d, Android: %d); dosya değiştirilmedi."
              % (len(ios_tr), len(paketler)), file=sys.stderr)
        return 1

    uygulamalar = []
    for k in sorted(set(ios_tr) | set(and_tr)):
        i, a = ios_tr.get(k), and_tr.get(k)
        ie, ae = ios_en.get(k), and_en.get(k)
        oz = ozetler.get(k, {})
        uyg = {
            "id": k,
            "ad": (i or a)["ad"],
            "aciklama": oz.get("tr") or (a and a["aciklama"]) or i["aciklama"],
            "ikon": (i or a)["ikon"],
            "ios": i and i["url"],
            "android": a and a["url"],
            "iosBundle": i and i["bundleId"],
            "androidPaket": a and a["paket"],
            "en": {
                "ad": (ie or ae or i or a)["ad"],
                "aciklama": oz.get("en") or (ae and ae["aciklama"]) or (ie and ie["aciklama"])
                            or (a and a["aciklama"]) or i["aciklama"],
            },
        }
        uygulamalar.append({x: y for x, y in uyg.items() if y is not None})

    uygulamalar.sort(key=lambda u: u["ad"].lower())
    eski = json.load(open(CIKTI, encoding="utf-8")) if os.path.exists(CIKTI) else {}
    if eski.get("uygulamalar") == uygulamalar:
        print("Değişiklik yok.")
        return 0
    yeni = {
        "surum": 1,
        "guncelleme": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uygulamalar": uygulamalar,
    }
    with open(CIKTI, "w", encoding="utf-8") as f:
        json.dump(yeni, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("%d uygulama yazıldı: %s" % (len(uygulamalar), ", ".join(u["ad"] for u in uygulamalar)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
