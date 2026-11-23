"""Asistencia semanal del personal propio de OCAS, sacada del libro de obra (MLDO), todas las obras,
agrupada por disciplina dentro de cada obra (la disciplina en que más días aparece cada trabajador).

Uso:  python herramientas/asistencia_semanal.py [lunes AAAA-MM-DD] [--publicar]
      (por defecto, el lunes de esta semana)
Escribe "Nomina personal/Asistencia semanal dd-mm al dd-mm-aaaa.html".
Con --publicar, además cifra cada semana y la sube a GitHub Pages (repo leonelcastillo/asistencia),
igual que el recorrido: la página pide la clave (archivo OCAS/.clave-asistencia, fuera del repo),
descifra en el teléfono y tiene un selector de semanas. Cada corrida rehace la semana actual y la
anterior (por si el libro se corrigió tarde) y crea las que falten desde INICIO.
Con --si-cambia publica solo si el libro cambió desde la última vez (huella.txt en el repo de la página).
Quien vigila es GitHub Actions (repo asistencia, .github/workflows/actualizar.yml, cada 5 min de 6:30 am a
7 pm, lu–sá) con los secretos MLDO_DB_URL (usuario de solo lectura) y ASISTENCIA_CLAVE: anda con la PC apagada.
La PC queda de respaldo con la tarea "OCAS Asistencia semanal" (Publicar asistencia.vbs, cada 30 min) y es la
que lleva a la nube los cambios de este script (copia en generar/), el logo y el workflow.
Marca: ✓ aparece en el libro · — hay reporte y no aparece · s/r el libro no tiene reporte ese día
(confirmar) · rayado: el día todavía no llega.
"""
import os, sys, html, base64, re
from datetime import date, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent  # raíz de OCAS (en la nube: raíz del repo asistencia)
NUBE = bool(os.environ.get("MLDO_DB_URL"))  # GitHub Actions: la llave llega como secreto
if NUBE:
    import psycopg2

    def q(sql, params=None):
        with psycopg2.connect(os.environ["MLDO_DB_URL"], connect_timeout=15) as c:
            c.set_session(readonly=True)
            with c.cursor() as cur:
                cur.execute(sql, params)
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
else:
    sys.path.insert(0, str(AQUI / "a168" / "scripts"))
    from mldo import q  # noqa: E402
LOGO_PNG = next(p for p in (AQUI / "nomina-contratistas/herramientas/plantillas/logo-ocas.png",
                            Path(__file__).resolve().parent / "logo-ocas.png") if p.exists())
WEB = Path(os.environ.get("ASISTENCIA_WEB") or AQUI / "herramientas" / "web-asistencia")  # clon del repo de la página
REPO = "leonelcastillo/asistencia"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

INICIO = date(2026, 11, 2)  # primera semana con personal propio en el libro
CODIGO = {  # opcional: forzar un código; las obras nuevas del libro se reconocen solas (ver codigos())
    "a168": "A-168", "villa-032-77456e": "V-032", "villa-v-425-90882a": "V-425",
          "villa-v-490-ocas-4e7ae2": "V-490"}
SEM = ["Lun", "Mar", "Mié", "Jue", "Vie"]
ACENTOS = {"plomeria": "plomería", "demolicion": "demolición", "albanileria": "albañilería"}
e = html.escape


def limpiar(p):
    m = re.search(r"\(([^)]*)\)", p)
    rol = m[1].strip().capitalize() if m else ""
    nombre = re.sub(r"\s*\([^)]*\)", "", p).strip()
    nombre = " ".join(w if w.isupper() and len(w) > 1 else w.capitalize() for w in nombre.split())
    return nombre, rol


def disciplina(d):
    d = " ".join((d or "Sin disciplina").lower().split())
    return " ".join(ACENTOS.get(w, w) for w in d.split()).capitalize()


def codigos():
    """Código corto de cada obra del libro (A-168, V-104…), sacado de su nombre: una obra nueva sale sola."""
    cod = {}
    for o in q("select obra_id, nombre from visor.obras"):
        m = re.search(r"\b([AV])\s*-?\s*0*(\d{2,3})\b", o["nombre"] or "", re.I) or \
            re.search(r"\b([AV])-?0*(\d{2,3})\b", o["obra_id"], re.I)
        cod[o["obra_id"]] = f"{m[1].upper()}-{int(m[2]):03d}" if m else (o["nombre"] or o["obra_id"]).strip()
    return {**cod, **CODIGO}


def rotulo(lunes):
    return f"{lunes:%d/%m} al {lunes + timedelta(days=4):%d/%m/%Y}"


def semana(lunes):
    """Devuelve (subtítulo, html del cuerpo, texto de resumen) de la semana que empieza ese lunes."""
    dias = [lunes + timedelta(days=i) for i in range(5)]
    fin = dias[-1]
    hoy = date.today()
    reportes = {(r["obra_id"], r["fecha"]) for r in q(
        "select obra_id, fecha from visor.reportes where tipo='apertura' and fecha between %s and %s", [lunes, fin])}
    filas = q("""select obra_id, fecha, persona, ausente, disciplina from visor.personal_diario
                 where origen='propio' and fecha between %s and %s""", [lunes, fin])
    COD = codigos()
    obras_ids = sorted({o for o, _ in reportes} | {r["obra_id"] for r in filas}, key=lambda o: COD.get(o, o))

    obras = {}
    for r in filas:
        nombre, rol = limpiar(r["persona"])
        p = obras.setdefault(r["obra_id"], {}).setdefault(nombre, {"rol": rol, "d": {}, "disc": {}})
        p["rol"] = p["rol"] or rol
        k = disciplina(r["disciplina"])
        p["disc"][k] = p["disc"].get(k, 0) + 1
        p["d"][r["fecha"]] = "aus" if r["ausente"] else "ok"

    cab = "".join(f"<th>{SEM[i]}<br><small>{d:%d/%m}</small></th>" for i, d in enumerate(dias))
    bloques, total_p, total_d, avisos, resumen = [], 0, 0, [], []
    for o in obras_ids:
        cod = COD.get(o, o)
        gente = obras.get(o, {})
        sin = [d for d in dias if (o, d) not in reportes and d <= hoy]
        if sin:
            avisos.append(f"{cod}: sin reporte el {', '.join(f'{SEM[dias.index(d)]} {d:%d/%m}' for d in sin)}")
        filas_html, grupos, n = [], {}, 0
        for nombre, p in gente.items():  # disciplina en la que más días aparece
            grupos.setdefault(max(p["disc"], key=p["disc"].get), []).append((nombre, p))
        for disc in sorted(grupos):
            filas_html.append(f'<tr class="disc"><td colspan="8">{e(disc)} <small>· {len(grupos[disc])}</small></td></tr>')
            for nombre, p in sorted(grupos[disc]):
                n += 1
                celdas, cuenta = [], 0
                for d in dias:
                    v = p["d"].get(d)
                    if v == "ok":
                        cuenta += 1
                        celdas.append('<td class="si">✓</td>')
                    elif v == "aus":
                        celdas.append('<td class="no">Ausente</td>')
                    elif d > hoy:  # día que todavía no llega
                        celdas.append('<td class="fut"></td>')
                    elif (o, d) not in reportes:
                        celdas.append('<td class="sr">s/r</td>')
                    else:
                        celdas.append('<td class="no">—</td>')
                total_p += 1
                total_d += cuenta
                rol = f' <span class="rol">{e(p["rol"])}</span>' if p["rol"] else ""
                filas_html.append(f'<tr><td class="n">{n}</td><td class="nom">{e(nombre)}{rol}</td>'
                                  f'{"".join(celdas)}<td class="tot">{cuenta}</td></tr>')
        if not filas_html:
            filas_html.append('<tr><td colspan="8" class="vacio">Sin personal propio en el libro esta semana</td></tr>')
        bloques.append(f"""<section><h2><span>{e(cod)}</span> {len(gente)} trabajador{'es' if len(gente) != 1 else ''}</h2>
<table><thead><tr><th>#</th><th class="nom">Trabajador</th>{cab}<th>Días</th></tr></thead>
<tbody>{''.join(filas_html)}</tbody></table></section>""")
        resumen.append(f"{cod} {sum(sum(v == 'ok' for v in p['d'].values()) for p in gente.values())} días / {len(gente)} pers.")

    aviso_html = "".join(f"<li>{e(a)}</li>" for a in avisos)
    sub = f"Semana del {rotulo(lunes)} · fuente: MiLibroDeObra · actualizado {datetime.now():%d/%m/%Y %I:%M %p}"
    cuerpo = f"""<div class="res"><div><b>{total_p}</b>trabajadores</div><div><b>{total_d}</b>días-hombre</div>
<div><b>{len([o for o in obras_ids if obras.get(o)])}</b>obras con personal propio</div></div>
{f'<div class="av"><b>Por confirmar</b><ul>{aviso_html}</ul></div>' if avisos else ''}
{''.join(bloques)}
<p class="ley">✓ aparece en el libro · — el libro tiene reporte ese día y no aparece · s/r el libro no tiene reporte ese día (confirmar con el ingeniero) · rayado: el día todavía no llega</p>
"""
    return sub, cuerpo, " · ".join(resumen + [f"AVISO {a}" for a in avisos])


LOGO = base64.b64encode(LOGO_PNG.read_bytes()).decode()

CSS = """:root{--v:#0f6e56;--vc:#e1f2eb;--o:#e0a000;--oc:#fdf3d8;--c:#17201c;--f:#f6f4ee}
*{box-sizing:border-box}
body{margin:0;background:var(--f);color:var(--c);font-family:Bahnschrift,"Segoe UI",sans-serif;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}
header{background:#fff;display:flex;align-items:center;gap:18px;padding:16px 24px}
header img{height:52px}
header h1{margin:0;font-size:22px} header p{margin:2px 0 0;color:#555;font-size:14px}
.acc{margin-left:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.rayas{height:8px;background:repeating-linear-gradient(45deg,var(--o) 0 12px,var(--c) 12px 24px)}
main{max-width:980px;margin:0 auto;padding:18px 16px 32px}
.res{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.res div{background:#fff;border-left:4px solid var(--v);padding:8px 14px;font-size:14px}
.res b{font-size:20px;display:block}
.av{background:var(--oc);border-left:4px solid var(--o);padding:8px 14px;margin:0 0 14px;font-size:14px}
.av ul{margin:4px 0 0;padding-left:18px}
section{background:#fff;margin-bottom:16px;padding:12px 14px;overflow-x:auto}
h2{margin:0 0 8px;font-size:16px;font-weight:500;color:#555}
h2 span{color:var(--v);font-weight:700;font-size:19px;margin-right:6px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border-bottom:1px solid #ddd;padding:5px 6px;text-align:center}
th{border-bottom:2px solid var(--c);font-weight:600} th small{font-weight:400;color:#666}
.nom{text-align:left} .n{color:#888;width:28px}
.rol{font-size:12px;color:#666}
.si{background:var(--vc);color:var(--v);font-weight:700}
.no{color:#999} .sr{background:var(--oc);color:#8a6400;font-size:12px}
.tot{font-weight:700} .fut{background:repeating-linear-gradient(45deg,#fff 0 4px,#f1f1f1 4px 8px)}
.disc td{text-align:left;font-weight:700;color:var(--v);border-bottom:1px solid var(--v);padding-top:10px}
.disc small{color:#888;font-weight:400} .vacio{color:#888;font-style:italic}
.ley{font-size:12px;color:#666}
.btn{flex-shrink:0;background:var(--v);color:#fff;border:0;border-radius:6px;padding:10px 16px;
  font:inherit;font-size:15px;cursor:pointer} .btn:hover{background:#0b5843}
#semana{font:inherit;font-size:15px;padding:9px 10px;border:2px solid var(--v);border-radius:6px;background:#fff;color:var(--c)}
@media(max-width:600px){header{padding:12px 16px;flex-wrap:wrap;gap:10px} header img{height:40px}
  header h1{font-size:18px} .acc{margin-left:0;width:100%} #semana{flex:1} th,td{padding:4px 3px;font-size:13px}}
@media print{.acc,#candado{display:none} body{background:#fff} main{padding:8px 0} section{padding:4px 0;break-inside:avoid}
  .rayas{height:0;border-top:2px solid var(--c)} .si,.sr,.fut{background:none} .res div,.av{background:none}}
"""

BOTON = ('<button class="btn" onclick="window.print()" '
         'title="En el destino elige Guardar como PDF para enviarlo">🖨 Imprimir / PDF</button>')


def pagina(sub, main, selector="", extra_head="", extra_body=""):
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Asistencia semanal</title>{extra_head}
<style>
{CSS}</style></head><body>
<header><img src="data:image/png;base64,{LOGO}" alt="OCAS"><div>
<h1>Asistencia semanal · personal propio</h1><p id="sub">{sub}</p></div>
<div class="acc">{selector}{BOTON}</div></header>
<div class="rayas"></div>
<main id="main">
{main}</main>{extra_body}</body></html>"""


# ---------- Página en línea (GitHub Pages, cifrada como el recorrido) ----------
CANDADO_CSS = """<meta name="robots" content="noindex">
<link rel="manifest" href="manifest.webmanifest"><meta name="theme-color" content="#0f6e56">
<link rel="icon" href="icon-192.png"><link rel="apple-touch-icon" href="icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Asistencia">
<style>
#instalar{display:none;background:#e0a000;color:#17201c}
#candado{position:fixed;inset:0;background:rgba(23,32,28,.92);display:flex;align-items:center;justify-content:center;padding:16px}
#candado .caja{background:#fff;padding:22px;border-radius:10px;max-width:340px;width:100%;border-top:6px solid #e0a000}
#candado input{width:100%;padding:10px;font:inherit;margin:8px 0;border:1px solid #bbb;border-radius:6px}
#candado .btn{margin:0;width:100%} #err{color:#b3261e;min-height:1em}
</style>"""

CANDADO_JS = """
<div id="candado"><div class="caja"><b>Asistencia semanal · OCAS</b>
<p>Escribe la clave. Solo se pide la primera vez en este equipo.</p>
<input id="clave" type="password" placeholder="Clave" autocomplete="current-password">
<button id="abrir" class="btn">Abrir</button><p id="err"></p></div></div>
<script>
const $ = id => document.getElementById(id);
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
let CLAVE = null;
async function descifrar(archivo, clave){
  const enc = await (await fetch(archivo + '?' + Date.now(), {cache:'no-store'})).json();
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(clave), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey({name:'PBKDF2', salt:b64(enc.salt), iterations:enc.iter, hash:'SHA-256'},
                                            base, {name:'AES-GCM', length:256}, false, ['decrypt']);
  const pt = await crypto.subtle.decrypt({name:'AES-GCM', iv:b64(enc.iv)}, key, b64(enc.data));
  return JSON.parse(new TextDecoder().decode(pt));
}
async function mostrar(lunes){
  $('sub').textContent = 'Cargando…';
  try { const d = await descifrar('semanas/' + lunes + '.enc', CLAVE);
        $('sub').textContent = d.sub; $('main').innerHTML = d.main;
        try { history.replaceState(null, '', '#' + lunes); } catch(e){}
  } catch(e){ $('sub').textContent = 'No pude abrir esa semana: ' + e.message; }
}
async function abrir(clave, guardar){
  try {
    const lista = await (await fetch('semanas.json?' + Date.now(), {cache:'no-store'})).json();
    const pedida = location.hash.slice(1);
    const elegida = lista.some(s => s.lunes === pedida) ? pedida : lista[0].lunes;
    await descifrar('semanas/' + elegida + '.enc', clave);  // valida la clave
    CLAVE = clave;
    $('semana').innerHTML = lista.map((s, i) =>
      `<option value="${s.lunes}">${i === 0 ? 'Esta semana · ' : ''}${s.rotulo}</option>`).join('');
    $('semana').value = elegida;
    $('semana').onchange = () => mostrar($('semana').value);
    $('candado').remove();
    if (guardar) try { localStorage.setItem('clave', clave); } catch(e){}
    await mostrar(elegida);
  } catch(e){
    $('err').textContent = e.name === 'OperationError' ? 'Clave incorrecta.' : 'No pude abrir: ' + e.message;
    try { localStorage.removeItem('clave'); } catch(e){}
  }
}
$('abrir').onclick = () => { const c = $('clave').value.trim(); if (c) abrir(c, true); };
$('clave').onkeydown = e => { if (e.key === 'Enter') $('abrir').click(); };
let guardada = null; try { guardada = localStorage.getItem('clave'); } catch(e){}
if (guardada) abrir(guardada, false); else $('clave').focus();
// Instalable en el teléfono: guarda la app y abre sin señal con lo último que vio
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
let aviso = null;
addEventListener('beforeinstallprompt', ev => { ev.preventDefault(); aviso = ev; $('instalar').style.display = 'inline-block'; });
$('instalar').onclick = async () => { if (!aviso) return; aviso.prompt(); await aviso.userChoice; aviso = null; $('instalar').style.display = 'none'; };
</script>"""


SW = """// Asistencia OCAS: primero internet (datos frescos); sin señal, lo último guardado.
const CACHE = 'asistencia-v1';
const BASE = ['./', 'index.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'semanas.json'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASE)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(caches.keys()
  .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  const clave = new Request(u.origin + u.pathname);  // sin el ?hora del cache-busting
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const c2 = r.clone(); caches.open(CACHE).then(c => c.put(clave, c2)); } return r; })
    .catch(() => caches.match(clave).then(g => g || (e.request.mode === 'navigate' ? caches.match('index.html') : Response.error()))));
});
"""


def instalable(web):
    """Manifiesto, service worker e íconos (logo OCAS sobre blanco con franja oro) para instalar en el teléfono."""
    import json
    from PIL import Image, ImageDraw
    (web / "manifest.webmanifest").write_text(json.dumps({
        "name": "Asistencia semanal OCAS", "short_name": "Asistencia", "start_url": "./", "scope": "./",
        "display": "standalone", "background_color": "#f6f4ee", "theme_color": "#0f6e56",
        "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (web / "sw.js").write_text(SW, encoding="utf-8")
    logo = Image.open(LOGO_PNG).convert("RGB")
    for lado in (192, 512):
        ic = Image.new("RGB", (lado, lado), "white")
        ancho = int(lado * 0.72)  # dentro de la zona segura de los íconos "maskable"
        l = logo.resize((ancho, int(logo.height * ancho / logo.width)), Image.LANCZOS)
        ic.paste(l, ((lado - l.width) // 2, (lado - l.height) // 2 - lado // 20))
        d, h, y = ImageDraw.Draw(ic), lado // 14, int(lado * 0.78)
        for x in range(-h, lado + h, h):  # franja de rayas oro/carbón de OCAS
            d.polygon([(x, y + h), (x + h // 2, y), (x + h, y), (x + h // 2, y + h)],
                      fill="#e0a000" if (x // h) % 2 == 0 else "#17201c")
        ic.save(web / f"icon-{lado}.png")


WORKFLOW = """name: Actualizar asistencia
# Revisa el libro cada 5 min de 6:30 am a 7 pm (hora de Venezuela, UTC-4), lu-sa, y publica solo si cambio.
on:
  schedule:
    - cron: "30,35,40,45,50,55 10 * * 1-6"
    - cron: "*/5 11-22 * * 1-6"
    - cron: "0 23 * * 1-6"
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: asistencia
  cancel-in-progress: false
jobs:
  actualizar:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      TZ: America/Caracas
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -q psycopg2-binary cryptography pillow
      - name: Publicar si el libro cambio
        env:
          MLDO_DB_URL: ${{ secrets.MLDO_DB_URL }}
          ASISTENCIA_CLAVE: ${{ secrets.ASISTENCIA_CLAVE }}
          ASISTENCIA_WEB: .
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          python generar/asistencia_semanal.py --si-cambia
"""


def preparar_clon():
    """En la PC, deja el clon de la página igual a lo publicado (es solo un espejo)."""
    import subprocess
    if NUBE:
        return
    if not WEB.exists():
        subprocess.run(["gh", "repo", "clone", REPO, str(WEB)], check=True)
        for k in ("user.name", "user.email"):  # la misma firma del repo OCAS
            v = subprocess.run(["git", "-C", str(AQUI), "config", k], capture_output=True, text=True).stdout.strip()
            subprocess.run(["git", "-C", str(WEB), "config", k, v], check=True)
    subprocess.run(["git", "-C", str(WEB), "fetch", "-q"], check=False)
    subprocess.run(["git", "-C", str(WEB), "reset", "-q", "--hard", "origin/main"], check=False)


def publicar(actual, h=None):
    import json, secrets, shutil, subprocess
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    clave = (os.environ.get("ASISTENCIA_CLAVE") or (AQUI / ".clave-asistencia").read_text(encoding="utf-8")).strip()
    if h is None:
        preparar_clon()

    b = lambda x: base64.b64encode(x).decode()
    carpeta = WEB / "semanas"
    carpeta.mkdir(exist_ok=True)
    lunes_todos, l = [], INICIO
    while l <= actual:
        lunes_todos.append(l)
        l += timedelta(days=7)
    for l in lunes_todos:
        f = carpeta / f"{l.isoformat()}.enc"
        if f.exists() and l < actual - timedelta(days=7):
            continue  # semanas viejas ya publicadas: no cambian
        sub, cuerpo, res = semana(l)
        sal, iv, it = secrets.token_bytes(16), secrets.token_bytes(12), 250000
        llave = PBKDF2HMAC(hashes.SHA256(), 32, sal, it).derive(clave.encode())
        datos = json.dumps({"sub": sub, "main": cuerpo}, ensure_ascii=False).encode()
        f.write_text(json.dumps({"salt": b(sal), "iv": b(iv), "iter": it,
                                 "data": b(AESGCM(llave).encrypt(iv, datos, None))}), encoding="utf-8")
        print(f"  semana {rotulo(l)}: {res}")
    (WEB / "semanas.json").write_text(json.dumps(
        [{"lunes": l.isoformat(), "rotulo": rotulo(l)} for l in reversed(lunes_todos)], ensure_ascii=False),
        encoding="utf-8")
    (WEB / "datos.enc").unlink(missing_ok=True)  # formato viejo (una sola semana)
    selector = ('<select id="semana" aria-label="Semana"></select>'
                '<button id="instalar" class="btn" type="button">📲 Instalar</button>')
    (WEB / "index.html").write_text(pagina("Cargando…", "", selector, CANDADO_CSS, CANDADO_JS), encoding="utf-8")
    (WEB / ".nojekyll").touch()
    instalable(WEB)
    (WEB / "README.md").write_text(
        "# Asistencia semanal\n\nPersonal propio por obra y disciplina, semana a semana. Los datos están cifrados; "
        "la página pide la clave. La actualiza GitHub Actions (.github/workflows/actualizar.yml) cada vez que "
        "el libro de obra cambia.\n", encoding="utf-8")
    if not NUBE:  # la PC lleva a la nube el código, el logo y el workflow (la nube no puede tocar su workflow)
        (WEB / "generar").mkdir(exist_ok=True)
        shutil.copy(__file__, WEB / "generar" / "asistencia_semanal.py")
        shutil.copy(LOGO_PNG, WEB / "generar" / "logo-ocas.png")
        (WEB / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (WEB / ".github" / "workflows" / "actualizar.yml").write_text(WORKFLOW, encoding="utf-8")
    if h:
        (WEB / "huella.txt").write_text(h)
    git = ["git", "-C", str(WEB)]
    subprocess.run(git + ["add", "-A"], check=True)
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode:
        quien = "nube" if NUBE else "PC"
        subprocess.run(git + ["commit", "-q", "-m",
                              f"Asistencia ({quien}): actualizacion {datetime.now():%d/%m/%Y %H:%M}"], check=True)
        if subprocess.run(git + ["push", "-q", "origin", "HEAD:main"]).returncode:
            print("Otro publicó primero (nube o PC): queda esa versión.")
            return
    print("Publicado: https://leonelcastillo.github.io/asistencia/")


def huella(lunes):
    """Resumen de lo que hay en el libro (semana actual y anterior): si no cambia, no hace falta publicar."""
    import hashlib
    desde, hasta = lunes - timedelta(days=7), lunes + timedelta(days=4)
    r = q("select obra_id, fecha, tipo from visor.reportes where fecha between %s and %s order by 1,2,3",
          [desde, hasta])
    p = q("""select obra_id, fecha, persona, ausente, disciplina from visor.personal_diario
             where origen='propio' and fecha between %s and %s order by 1,2,3""", [desde, hasta])
    o = q("select obra_id, nombre from visor.obras order by 1")
    return hashlib.sha256(repr((date.today(), r, p, o)).encode()).hexdigest()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lunes = date.fromisoformat(args[0]) if args else date.today() - timedelta(days=date.today().weekday())
    h = None
    if "--si-cambia" in sys.argv:  # vigilancia: publica solo si una obra abrió o cambió algo
        preparar_clon()
        h = huella(lunes)
        marca = WEB / "huella.txt"  # la comparten la nube y la PC (va en el repo)
        if marca.exists() and marca.read_text().strip() == h:
            sys.exit(0)
        print(f"{datetime.now():%d/%m %H:%M} cambio en el libro: publico")
    if not NUBE:
        sub, cuerpo, res = semana(lunes)
        salida = AQUI / "Nomina personal" / f"Asistencia semanal {lunes:%d-%m} al {lunes + timedelta(days=4):%d-%m-%Y}.html"
        salida.write_text(pagina(sub, cuerpo), encoding="utf-8")
        print(salida)
        print(" ", res)
    if "--publicar" in sys.argv or "--si-cambia" in sys.argv:
        publicar(lunes, h)
