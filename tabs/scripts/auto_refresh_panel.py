# tabs/scripts/auto_refresh_panel.py

import math, time as _t
from datetime import datetime, timedelta
from typing import Iterable, Optional, Tuple, Any

def auto_refresh_panel(
    st,
    interval_minutes: float = 5,
    key: str = "ayarlar_auto5m",
    panel_title: str = "⏱ Otomatik Saat & Rastgele Mesaj",
    messages: Optional[Iterable[str]] = None,
    timezone: str = "Europe/Istanbul",
    expanded: bool = True,
    show_fullscreen_message: bool = True,
    message_text: str = "🔄 Güncelleme devam ediyor…",
    message_duration_sec: int = 5,
    # — yeni parametreler —
    show_controls: bool = True,         # panel içi ayar butonları
    start_paused: bool = False,         # sayfa açılışında duraklat
    active_hours: Optional[Tuple[int,int]] = None,  # ör. (22, 6) gece modu (gece 22 → sabah 06)
    show_progress: bool = True,         # ilerleme çubuğu göster
    # — eklenen parametreler —
    message_mode: str = "random",       # "random" | "rotate"
    align_to_wall_clock: bool = True,   # True: 5dk ise :00,:05,:10 hizası
    beep_on_overlay: bool = False,      # True: overlay açılırken kısa beep
    silent: bool = False,               # True: minimum yazı/bildirim

    # — otomatik revize entegrasyonu —
    conn: Optional[Any] = None,         # SQLite/DB bağlantısı (opsiyonel)
    enable_revize_controls: bool = False,   # panelde "Otomatik Revize" butonu göster
    revize_donem: Optional[str] = "127",    # butonla çalışacak dönem (varsayılan 127)
):
    """
    Streamlit içinde periyodik autorefresh paneli.
    Yenilemeden *message_duration_sec* saniye önce tam ekran 'Güncelleme devam ediyor…' overlay'i gösterir.
    • show_controls=True ise panel içinde durdur/başlat, test ve şimdi yenile gibi butonlar gelir.
    • active_hours=(start_h, end_h) verilirse sadece bu saat aralığında (*timezone*) çalışır.
      Örn: (22,6) => 22:00–06:00 arası aktif (gece modu). (8,17) => 08:00–17:00 arası aktif (gündüz).
    • align_to_wall_clock=True ile interval dakika bazlı ise gerçek duvar saatine hizalanır.

    • enable_revize_controls=True ise, conn ve revize_donem ile birlikte panel içine
      '🛠️ Otomatik Revize' butonu eklenir. Butona basıldığında:
          adet = otomatik_global_revize(conn, donem=revize_donem)
          st.success(f"{revize_donem}. dönem için otomatik revize tamam: {adet} satır güncellendi.")
    """
    import random
    import streamlit.components.v1 as components

    if messages is None:
        messages = [
            "Gökler bizim!", "Checklist tamam mı?", "Uçuş güvenliği önce gelir.",
            "Rüzgâr uygun, plan hazır 😎", "Bugün harika uçuşlar!", "Briefing zamanı!"
        ]
    messages = list(messages)

    # ---- yardımcılar ----
    def _now_str(tz_name: str) -> str:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _now_obj(tz_name: str) -> datetime:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            return datetime.now()

    def _is_active_hour(now_dt: datetime, rng: Optional[Tuple[int,int]]) -> bool:
        if not rng:
            return True
        sh, eh = rng
        h = now_dt.hour
        if sh == eh:
            return True  # 24 saat
        if sh < eh:
            return (sh <= h < eh)  # aynı gün aralığı (örn 08–17)
        # geceye saran aralık (örn 22–06)
        return (h >= sh) or (h < eh)

    # kalan saniyeyi harici kullanmak istersek:
    def get_next_refresh_seconds(total_seconds: int) -> int:
        if total_seconds <= 0:
            return 0
        return total_seconds - (math.floor(_t.time()) % total_seconds)

    # ---- durum/ayar state'leri ----
    # panel bazlı kalıcı ayarlar (kullanıcı değişikliklerini hatırla)
    ss = st.session_state
    _pfx = f"arp__{key}"
    pause_state_key = f"{_pfx}__paused"
    if pause_state_key not in ss:
        ss[pause_state_key] = bool(start_paused)

    # kullanıcıya ayar sunulacaksa panel içinde değerleri state ile yöneteceğiz
    # ilk değerler: fonksiyon parametreleri
    if f"{_pfx}__interval" not in ss:
        ss[f"{_pfx}__interval"] = float(interval_minutes)
    if f"{_pfx}__overlay" not in ss:
        ss[f"{_pfx}__overlay"] = bool(show_fullscreen_message)
    if f"{_pfx}__msg" not in ss:
        ss[f"{_pfx}__msg"] = str(message_text)
    if f"{_pfx}__msgdur" not in ss:
        ss[f"{_pfx}__msgdur"] = int(message_duration_sec)

    user_interval_minutes = ss[f"{_pfx}__interval"]
    user_message_text = ss[f"{_pfx}__msg"]
    user_message_duration = ss[f"{_pfx}__msgdur"]
    user_overlay_on = ss[f"{_pfx}__overlay"]

    # mesaj rotasyon sayacı
    if f"{_pfx}__msg_idx" not in ss:
        ss[f"{_pfx}__msg_idx"] = 0

    # ---- PANEL ----
    with st.expander(f"{panel_title}", expanded=expanded):

        # üst kısım: anlık saat ve mesaj
        now_obj = _now_obj(timezone)
        now_str = _now_str(timezone)
        st.metric("Şu an", now_str)

        # mesaj seçimi
        if message_mode == "rotate" and messages:
            msg = messages[ss[f"{_pfx}__msg_idx"] % len(messages)]
            ss[f"{_pfx}__msg_idx"] += 1
        else:
            msg = random.choice(messages) if messages else ""
        if not silent and msg:
            st.success(msg)

        # panel içi kontroller (opsiyonel)
        extra_cols = 0
        if show_controls:
            # kolon düzeni: [otomatik toggle] [şimdi yenile] [overlay test] [ayarlar] [revize butonu?]
            show_revize_btn = bool(enable_revize_controls and conn is not None and revize_donem)
            cols_spec = [1, 1, 1, 2] + ([2] if show_revize_btn else [])
            cols = st.columns(cols_spec)

            # c1: otomatik toggle
            try:
                onoff = cols[0].toggle("⏯ Otomatik", value=not ss[pause_state_key], key=f"{key}_tgl")
            except Exception:
                onoff = cols[0].checkbox("⏯ Otomatik", value=not ss[pause_state_key], key=f"{key}_tgl")
            ss[pause_state_key] = (not onoff)

            # c2: şimdi yenile
            if cols[1].button("♻️ Şimdi yenile", key=f"{key}_force"):
                st.rerun()

            # c3: overlay test
            if cols[2].button("🧪 Overlay Test (2 sn)", key=f"{key}_testbtn"):
                ss[f"{key}_test_overlay"] = True

            # c4: ayarlar
            with cols[3]:
                st.caption("Ayarlar")
                ss[f"{_pfx}__interval"] = st.number_input(
                    "Yenileme (dk)", min_value=0.1, max_value=120.0,
                    step=0.1, value=float(ss[f"{_pfx}__interval"]), key=f"{key}_intv"
                )
                ss[f"{_pfx}__overlay"] = st.checkbox(
                    "Tam ekran mesaj", value=bool(ss[f"{_pfx}__overlay"]), key=f"{key}_ovl"
                )
                ss[f"{_pfx}__msg"] = st.text_input(
                    "Mesaj", value=ss[f"{_pfx}__msg"], key=f"{key}_msg"
                )
                ss[f"{_pfx}__msgdur"] = st.number_input(
                    "Mesaj süresi (sn)", min_value=1, max_value=120,
                    value=int(ss[f"{_pfx}__msgdur"]), step=1, key=f"{key}_mdur"
                )

            # c5: (opsiyonel) otomatik revize
            if show_revize_btn:
                with cols[4]:
                    st.caption("Revize")
                    if st.button(f"🛠️ Otomatik Revize (Dönem {revize_donem})", key=f"{key}_revize_btn"):
                        try:
                            # içe aktarma: fonksiyonun modülü projenizde değişebilir
                            try:
                                from tabs.scripts.auto_ileriden_gelen import otomatik_global_revize  # type: ignore
                            except Exception:
                                # alternatif import yolu: gerekirse burayı kendi projenize göre ayarlayın
                                from tabs.scripts.auto_ileriden_gelen import otomatik_global_revize  # type: ignore

                            adet = otomatik_global_revize(conn, donem=str(revize_donem))
                            st.success(f"{revize_donem}. dönem için otomatik revize tamam: {adet} satır güncellendi.")
                        except Exception as e:
                            st.error(f"Otomatik revize çalıştırılamadı: {e}")

        # son kullanıcı ayarlarını tekrar çek
        user_interval_minutes = float(ss[f"{_pfx}__interval"])
        user_message_text = ss[f"{_pfx}__msg"]
        user_message_duration = int(ss[f"{_pfx}__msgdur"])
        user_overlay_on = bool(ss[f"{_pfx}__overlay"])

        # aktif saat kontrolü
        aktif = _is_active_hour(now_obj, active_hours)
        if active_hours and not silent:
            sh, eh = active_hours
            aralik = f"{sh:02d}:00–{eh:02d}:00"
            st.caption(f"⏳ Aktif saat aralığı: {aralik} ({timezone})")

        # otomatik yenileme açık mı?
        paused = bool(ss[pause_state_key])
        can_refresh = (not paused) and aktif

        # interval ve ms
        interval_minutes = max(0.0, float(user_interval_minutes))
        # duvar saatine hizalama (yalnız dakikalık aralıklar için anlamlı)
        if align_to_wall_clock and interval_minutes > 0:
            # ör: 5 dk -> bir sonraki çoklu dakikaya kalan saniye
            step = int(round(interval_minutes * 60))
            # now_obj ile hizalı kalan saniye:
            now_sec = now_obj.minute * 60 + now_obj.second
            remain = step - (now_sec % step)
            # çok küçük kalmışsa (örn 1-2 sn), kullanıcıya daha düzgün görünmesi için min 3 sn
            if remain < 3:
                remain += step
            interval_ms = int(remain * 1000)
            toplam_sn = step  # progress için sabit periyot
        else:
            interval_ms = int(interval_minutes * 60 * 1000)
            toplam_sn = max(1, int(interval_minutes * 60))

        # 1) Autorefresh kur (gerekirse)
        count = None
        used_autorefresh = False
        if can_refresh and interval_ms > 0:
            try:
                from streamlit_autorefresh import st_autorefresh
                count = st_autorefresh(interval=interval_ms, key=key)
                used_autorefresh = True
                if not silent:
                    st.caption(f"Otomatik yenileme: **AKTİF** • sayaç: {count}")
            except Exception:
                if not silent:
                    st.caption("Otomatik yenileme: **Yedek JS modu** (streamlit-autorefresh bulunamadı)")
        else:
            if not silent:
                durum = "DURAKLATILDI" if paused else "SAAT DIŞI"
                st.caption(f"Otomatik yenileme: **{durum}**")

        # 2) FULL-SCREEN overlay (JS + opsiyonel beep)
        test_overlay = bool(ss.get(f"{key}_test_overlay", False))
        if user_overlay_on:
            # yenilemeden önceki süre (ms)
            before_ms = max(0, interval_ms - int(user_message_duration) * 1000) if can_refresh and interval_ms > 0 else 0
            # WebAudio API ile kısa beep üretimi (harici dosya yok)
            js_beep = """
              try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.value = 880;
                gain.gain.setValueAtTime(0.0001, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.01);
                gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);
                osc.connect(gain); gain.connect(ctx.destination);
                osc.start();
                setTimeout(() => { osc.stop(); ctx.close(); }, 220);
              } catch(e) {}
            """ if beep_on_overlay else ""

            components.html(
                f"""
                <style>
                  #guncelleme_overlay_{key} {{
                    position: fixed; inset: 0;
                    display: none; align-items: center; justify-content: center;
                    background: rgba(15,23,42,.94); color: #fff;
                    z-index: 999999999;
                    font-size: clamp(18px, 3.2vw, 42px); font-weight: 800;
                    letter-spacing: .4px; text-align: center;
                  }}
                </style>
                <div id="guncelleme_overlay_{key}">{user_message_text}</div>
                <script>
                (function() {{
                  const overlay = document.getElementById("guncelleme_overlay_{key}");
                  if (!overlay) return;

                  const canRefresh = {str(can_refresh).lower()};
                  const intervalMs = {interval_ms};
                  const msgDurMs   = {int(user_message_duration) * 1000};
                  const testNow    = {str(test_overlay).lower()};

                  function openOverlay() {{
                    overlay.style.display = "flex";
                    {js_beep}
                    setTimeout(() => overlay.style.display = "none", msgDurMs + 8000);
                  }}

                  // Test düğmesi: 2 sn göster
                  if (testNow) {{
                    overlay.style.display = "flex";
                    setTimeout(() => overlay.style.display = "none", 2000);
                  }}

                  if (canRefresh && intervalMs > 0) {{
                    // Yenilemeden hemen önce overlay'i aç
                    setTimeout(() => {{
                      openOverlay();
                    }}, Math.max(0, intervalMs - msgDurMs));

                    // Yedek JS modunda sayfayı yenile
                    {'' if used_autorefresh else 'setTimeout(() => window.parent.location.reload(), intervalMs);'}
                  }}
                }})();
                </script>
                """,
                height=0, width=0
            )
        # test bayrağını sıfırla
        if test_overlay:
            ss[f"{key}_test_overlay"] = False

        # 3) Geri sayım + ilerleme çubuğu + bir sonraki saat
        kalan_sn = get_next_refresh_seconds(toplam_sn) if can_refresh and toplam_sn > 0 else 0

        if show_progress and can_refresh and toplam_sn > 0:
            try:
                pct = int(round((toplam_sn - kalan_sn) / toplam_sn * 100))
                st.progress(pct, text=None if silent else f"Bir sonraki otomatik yenileme ≈ {kalan_sn} sn sonra")
            except Exception:
                if not silent:
                    st.caption(f"Bir sonraki otomatik yenileme ≈ {kalan_sn} sn sonra")

            try:
                next_at = (_now_obj(timezone) + timedelta(seconds=kalan_sn)).strftime("%H:%M:%S")
                if not silent:
                    st.caption(f"🕒 Planlanan yenileme zamanı: {next_at} ({timezone})")
            except Exception:
                pass

        # 4) Bilgilendirme mesajı
        if not can_refresh and not silent:
            if paused:
                st.info("⏸ Otomatik yenileme duraklatıldı. '⏯ Otomatik' anahtarını açın veya '♻️ Şimdi yenile'ye basın.")
            elif not aktif:
                st.info("🕘 Belirlenen saat aralığı dışında. Aralık içinde otomatikleşecek.")

    # dönüş
    return {
        "count": count,
        "now": now_str,
        "paused": bool(ss[pause_state_key]),
        "active_hours_ok": bool(aktif),
        "interval_minutes": float(interval_minutes),
        "get_next_refresh_seconds": lambda: kalan_sn,
        "aligned": bool(align_to_wall_clock),
    }
