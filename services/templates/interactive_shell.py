from __future__ import annotations

import html
import re
from typing import Any, Iterable


def _value(item: Any, name: str, default: str = "") -> str:
    if isinstance(item, dict):
        return str(item.get(name, default) or default)
    return str(getattr(item, name, default) or default)


def _safe_id(value: str, fallback: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-")
    return result[:64] or fallback


def render_interactive_shell(
    *,
    title: str,
    sections: Iterable[Any],
    interaction_js: str = "",
    custom_css: str = "",
) -> str:
    """Render generated content inside the trusted, reusable EduAI application shell."""
    normalized = []
    seen = set()
    for index, section in enumerate(sections, start=1):
        section_id = _safe_id(_value(section, "id"), f"section-{index}")
        base = section_id
        suffix = 2
        while section_id in seen:
            section_id = f"{base}-{suffix}"
            suffix += 1
        seen.add(section_id)
        normalized.append(
            {
                "id": section_id,
                "label": _value(section, "label", f"Раздел {index}")[:80],
                "html": _value(section, "html"),
            }
        )
    if not normalized:
        normalized = [{"id": "content", "label": "Материал", "html": "<p>Материал не сформирован.</p>"}]

    nav = "".join(
        f'<button class="eduai-nav__item" type="button" role="tab" aria-selected="{str(i == 0).lower()}" '
        f'aria-controls="panel-{section["id"]}" data-eduai-tab="{section["id"]}">{html.escape(section["label"])}</button>'
        for i, section in enumerate(normalized)
    )
    panels = "".join(
        f'<section class="eduai-panel" id="panel-{section["id"]}" role="tabpanel" '
        f'data-eduai-panel="{section["id"]}" {"" if i == 0 else "hidden"}>'
        f'<div class="eduai-panel__heading"><span class="eduai-kicker">EduAI</span>'
        f'<h2>{html.escape(section["label"])}</h2></div>'
        f'<div class="eduai-content">{section["html"]}</div></section>'
        for i, section in enumerate(normalized)
    )
    safe_title = html.escape(str(title or "EduAI Interactive")[:180])

    return f'''<!doctype html>
<html lang="ru" data-eduai-shell="1">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{safe_title}</title>
<style data-eduai-shell-style>
:root{{--eduai-bg:#07111f;--eduai-panel:#0d1c30;--eduai-panel-2:#12263f;--eduai-text:#f5f8fc;--eduai-muted:#aec0d4;--eduai-accent:#71e4ca;--eduai-accent-2:#8db7ff;--eduai-border:rgba(255,255,255,.12);--eduai-shadow:0 18px 45px rgba(0,0,0,.26);--eduai-radius:20px}}
*{{box-sizing:border-box}}html{{min-width:0;background:var(--eduai-bg)}}body{{margin:0;min-width:0;color:var(--eduai-text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 12% -10%,rgba(113,228,202,.18),transparent 36rem),radial-gradient(circle at 92% 0,rgba(141,183,255,.16),transparent 34rem),var(--eduai-bg);line-height:1.55;overflow-x:hidden}}
button,input,select,textarea{{font:inherit}}button{{cursor:pointer}}a{{color:inherit}}img,svg,canvas,video{{max-width:100%;height:auto}}svg{{max-height:520px}}code,pre{{max-width:100%;overflow:auto}}table{{width:100%;border-collapse:collapse;display:block;overflow:auto}}th,td{{padding:.65rem .8rem;border-bottom:1px solid var(--eduai-border);text-align:left}}
.eduai-app{{width:min(1180px,100%);margin:0 auto;padding:clamp(12px,2.5vw,28px)}}.eduai-header{{display:flex;gap:18px;align-items:center;justify-content:space-between;padding:clamp(18px,3vw,30px);border:1px solid var(--eduai-border);border-radius:var(--eduai-radius);background:linear-gradient(135deg,rgba(18,38,63,.95),rgba(13,28,48,.88));box-shadow:var(--eduai-shadow)}}
.eduai-brand{{display:flex;gap:14px;align-items:center;min-width:0}}.eduai-logo{{width:46px;height:46px;border-radius:15px;display:grid;place-items:center;background:linear-gradient(135deg,var(--eduai-accent),var(--eduai-accent-2));color:#06111e;font-weight:900;box-shadow:0 8px 22px rgba(113,228,202,.22)}}.eduai-header h1{{font-size:clamp(1.2rem,3vw,2rem);line-height:1.15;margin:.2rem 0;overflow-wrap:anywhere}}.eduai-subtitle{{margin:0;color:var(--eduai-muted);font-size:.92rem}}
.eduai-nav{{display:flex;gap:8px;overflow:auto;padding:12px 2px 4px;margin:14px 0;scrollbar-width:thin}}.eduai-nav__item{{flex:0 0 auto;border:1px solid var(--eduai-border);background:rgba(13,28,48,.86);color:var(--eduai-muted);border-radius:999px;padding:10px 15px;transition:transform .16s ease,background .16s ease,color .16s ease,border-color .16s ease}}.eduai-nav__item:hover{{transform:translateY(-1px);color:var(--eduai-text)}}.eduai-nav__item:focus-visible{{outline:3px solid rgba(113,228,202,.35);outline-offset:2px}}.eduai-nav__item[aria-selected="true"]{{color:#06111e;background:linear-gradient(135deg,var(--eduai-accent),var(--eduai-accent-2));border-color:transparent;font-weight:750}}
.eduai-panel{{border:1px solid var(--eduai-border);border-radius:var(--eduai-radius);background:rgba(13,28,48,.9);box-shadow:var(--eduai-shadow);padding:clamp(18px,3vw,32px);min-width:0}}.eduai-panel[hidden]{{display:none!important}}.eduai-panel__heading{{margin-bottom:16px}}.eduai-panel h2{{font-size:clamp(1.25rem,2.4vw,1.8rem);margin:.1rem 0}}.eduai-kicker{{font-size:.76rem;text-transform:uppercase;letter-spacing:.12em;color:var(--eduai-accent);font-weight:800}}
.eduai-content{{min-width:0}}.eduai-content>:first-child{{margin-top:0}}.eduai-content> :last-child{{margin-bottom:0}}.eduai-content .card,.eduai-card{{background:var(--eduai-panel-2);border:1px solid var(--eduai-border);border-radius:16px;padding:clamp(14px,2.3vw,22px);min-width:0}}.eduai-content .grid,.eduai-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:14px}}.eduai-content button,.eduai-button{{border:1px solid transparent;background:linear-gradient(135deg,var(--eduai-accent),var(--eduai-accent-2));color:#06111e;font-weight:750;border-radius:12px;padding:10px 14px;transition:transform .15s ease,filter .15s ease}}.eduai-content button:hover{{filter:brightness(1.05);transform:translateY(-1px)}}.eduai-content button:focus-visible,.eduai-content input:focus-visible,.eduai-content select:focus-visible,.eduai-content textarea:focus-visible{{outline:3px solid rgba(113,228,202,.35);outline-offset:2px}}.eduai-content input,.eduai-content select,.eduai-content textarea{{max-width:100%;border:1px solid var(--eduai-border);background:#09182a;color:var(--eduai-text);border-radius:11px;padding:9px 11px}}
.eduai-modal{{position:fixed;inset:0;display:none;place-items:center;padding:18px;background:rgba(0,0,0,.62);z-index:20}}.eduai-modal[data-open="true"]{{display:grid}}.eduai-modal__dialog{{width:min(640px,100%);max-height:min(80vh,760px);overflow:auto;background:var(--eduai-panel);border:1px solid var(--eduai-border);border-radius:var(--eduai-radius);padding:22px;box-shadow:var(--eduai-shadow)}}.eduai-footer{{padding:20px 4px 4px;text-align:center;color:var(--eduai-muted);font-size:.82rem}}
@media (max-width:720px){{.eduai-app{{padding:10px}}.eduai-header{{align-items:flex-start;padding:17px}}.eduai-logo{{width:40px;height:40px;border-radius:13px}}.eduai-panel{{padding:16px;border-radius:16px}}.eduai-nav{{margin-top:10px}}.eduai-content .grid,.eduai-grid{{grid-template-columns:1fr}}}}
@media (prefers-reduced-motion:reduce){{*,*::before,*::after{{scroll-behavior:auto!important;transition:none!important;animation:none!important}}}}
{custom_css[:18000]}
</style>
</head>
<body>
<div class="eduai-app">
<header class="eduai-header"><div class="eduai-brand"><div class="eduai-logo" aria-hidden="true">E</div><div><p class="eduai-subtitle">Интерактивный учебный модуль</p><h1>{safe_title}</h1></div></div></header>
<nav class="eduai-nav" aria-label="Разделы приложения" role="tablist">{nav}</nav>
<main>{panels}</main>
<footer class="eduai-footer">EduAI · интерактивное обучение</footer>
</div>
<div class="eduai-modal" id="eduai-modal" aria-hidden="true"><div class="eduai-modal__dialog" role="dialog" aria-modal="true"><div id="eduai-modal-content"></div><p><button type="button" data-eduai-modal-close>Закрыть</button></p></div></div>
<script data-eduai-shell-script>
(()=>{{
 const tabs=[...document.querySelectorAll('[data-eduai-tab]')]; const panels=[...document.querySelectorAll('[data-eduai-panel]')];
 const activate=id=>{{tabs.forEach(t=>t.setAttribute('aria-selected',String(t.dataset.eduaiTab===id)));panels.forEach(p=>p.hidden=p.dataset.eduaiPanel!==id);}};
 tabs.forEach(tab=>tab.addEventListener('click',()=>activate(tab.dataset.eduaiTab)));
 const modal=document.getElementById('eduai-modal'); const modalContent=document.getElementById('eduai-modal-content');
 window.EduAIShell=Object.freeze({{showSection:activate,openModal(content){{modalContent.textContent=String(content??'');modal.dataset.open='true';modal.setAttribute('aria-hidden','false');}},closeModal(){{modal.dataset.open='false';modal.setAttribute('aria-hidden','true');}}}});
 document.addEventListener('click',e=>{{if(e.target.closest('[data-eduai-modal-close]')) window.EduAIShell.closeModal();}});
}})();
</script>
<script data-eduai-generated-logic>{interaction_js[:50000]}</script>
</body>
</html>'''
