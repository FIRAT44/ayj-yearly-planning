# tabs/scripts/auto_refresh_panel.py

import math, time as _t
from datetime import datetime, timedelta, time as dt_time
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
    Streamlit icinde periyodik autorefresh paneli.
    - show_controls=True ise panel icinde durdur/baslat, test ve simdi yenile gibi butonlar gosterilir.
    - active_hours parametresi verilirse yalnizca bu saat araliginda (*timezone*) calisir.
    - align_to_wall_clock=True duvar saatine hizali calismayi saglar.
    - enable_revize_controls=True ve kullanilabilir bir baglanti verildiginde revize otomasyonu panelde gosterilir.
    """
    import random
    import streamlit.components.v1 as components

            if enable_revize_controls and conn is not None:
                if scheduler_error:
                    st.error(f'Otomatik revize ayarlari yuklenemedi: {scheduler_error}')
                elif scheduler is not None:
                    cfg = scheduler.config
                    with st.expander('Genel tarama otomasyonu', expanded=False):
                        st.caption('Tum donemler icin genel tarama ve revizeyi planlayin.')
                        enabled_default = bool(cfg.get('enabled', False))
                        time_str = cfg.get('run_time', '02:00')
                        try:
                            hour, minute = [int(part) for part in time_str.split(':')[:2]]
                            time_default = dt_time(hour, minute)
                        except Exception:
                            time_default = dt_time(2, 0)

                        enabled_toggle = st.checkbox('Gunluk otomatik revizeyi etkinlestir', value=enabled_default, key=f"{key}_revize_enabled")
                        selected_time = st.time_input('Calisma saati', value=time_default, step=timedelta(minutes=5), key=f"{key}_revize_time")

                        col_save, col_run = st.columns(2)
                        if col_save.button('Ayarleri kaydet', key=f"{key}_revize_save"):
                            cfg['enabled'] = bool(enabled_toggle)
                            cfg['run_time'] = selected_time.strftime('%H:%M')
                            scheduler.config = cfg
                            scheduler.save_config()
                            st.success('Otomatik revize ayarlari guncellendi.')

                        if col_run.button('Simdi calistir', key=f"{key}_revize_run"):
                            run_now_result = scheduler.run_now(conn)
                            status_now = run_now_result.get('status')
                            summary_now = run_now_result.get('summary', {})
                            if status_now == 'completed':
                                st.success(f"Revize tamamlandi: {summary_now.get('gorev_sayisi', 0)} gorev guncellendi.")
                            elif status_now == 'no_missing':
                                st.info('Revize calisti ancak guncellenecek kayit bulunmadi.')
                            elif status_now == 'no_period':
                                st.warning('Veritabanda planlanan donem bulunamadi.')
                            else:
                                st.error(f"Revize tamamlanamadi: {status_now}.")
                            if run_now_result.get('log_path'):
                                st.caption(f"Log: {run_now_result['log_path']}")

                        last_status = cfg.get('last_run_status')
                        last_date = cfg.get('last_run_date')
                        if last_status:
                            st.caption(f"Son durum: {last_status} ({last_date})")
                        if cfg.get('last_run_log'):
                            st.caption(f"Son log dosyasi: {cfg['last_run_log']}")
                        if scheduler_result and scheduler_result.get('ran') and scheduler_result.get('reason') != 'forced':
                            auto_summary = scheduler_result.get('summary', {})
                            st.success(f"Planlanan otomatik revize tamamlandi: {auto_summary.get('gorev_sayisi', 0)} gorev guncellendi.")
                            if scheduler_result.get('log_path'):
                                st.caption(f"Log: {scheduler_result['log_path']}")

            # son kullanici ayarlarini tekrar cek
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
