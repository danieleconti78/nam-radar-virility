#!/usr/bin/env python3
"""
proteggi.py — mette site/index.html dietro una password.

    RADAR_PASSWORD=... python3 tools/proteggi.py

GitHub Pages serve solo file statici, quindi la protezione non puo' stare sul server:
la pagina viene cifrata intera (dati, copy, lettura del mercato) e il browser la
decifra con la password (PBKDF2-SHA256, 600k iterazioni, AES-256-GCM). Senza la
password nel sorgente pubblicato c'e' solo testo cifrato.

I file in media/ e v/ restano in chiaro: si chiamano con l'id dell'inserzione e sono
creativita' gia' pubbliche nella Ad Library. Chi non ha la password non sa quali sono.

Colori e logo della schermata d'ingresso stanno in competitors.json:
cliente.ingresso = {"bg", "card", "ink", "muted", "line", "accent", "logo", "font"}.
"""
import base64, json, os, sys

ITERAZIONI = 600_000
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SHELL = r"""<!doctype html>
<html lang="it"><head>
<meta charset="utf-8">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITOLO__</title>
__FONT__
<script>try{if(sessionStorage.getItem("__CHIAVE__"))document.documentElement.classList.add("riapre");}catch(e){}</script>
<style>
:root{--bg:__BG__;--card:__CARD__;--ink:__INK__;--muted:__MUTED__;--line:__LINE__;--accent:__ACCENT__;--err:#b4471f;color-scheme:light}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font:15px/1.5 __FAMIGLIA__}
main{width:min(400px,calc(100% - 32px));background:var(--card);border:1px solid var(--line);border-radius:16px;padding:30px 26px;text-align:center}
.logo{display:block;margin:0 auto 14px;height:56px;width:auto}
h1{font-size:22px;margin:0 0 6px;letter-spacing:-.01em;font-weight:600}
p{color:var(--muted);margin:0 0 18px;font-size:14px}
form{text-align:left}
label{display:block;font-size:12px;color:var(--muted);margin-bottom:6px}
input{width:100%;font:inherit;padding:11px 14px;border:1px solid var(--line);border-radius:999px;background:#fff;color:var(--ink)}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
button{margin-top:14px;width:100%;font:inherit;font-weight:600;padding:11px 14px;border:0;border-radius:999px;background:var(--accent);color:#fff;cursor:pointer}
button:disabled{opacity:.65;cursor:progress}
#err{color:var(--err);min-height:1.2em;margin:10px 0 0;font-size:13px;text-align:center}
#wait{display:none}
.riapre #gate{display:none}
.riapre #wait{display:block}
</style></head><body>
<main>
__LOGO__
<h1>__TITOLO__</h1>
<p id="wait">Apro la pagina&hellip;</p>
<form id="gate" autocomplete="on">
<p>Pagina riservata. La password resta in questo browser e non viene inviata a nessun server.</p>
<label for="pw">Password</label>
<input id="pw" name="password" type="password" autocomplete="current-password" autocapitalize="off" spellcheck="false" required autofocus>
<button type="submit" id="go">Entra</button>
<p id="err" hidden></p>
</form>
</main>
<script type="application/json" id="payload">__PAYLOAD__</script>
<script>
const P = JSON.parse(document.getElementById("payload").textContent);
const KEY = "__CHIAVE__";
const err = document.getElementById("err"), go = document.getElementById("go");
function b64(s){const b=atob(s);const u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u}
function messaggio(t){err.hidden=!t;err.textContent=t||""}
async function decifra(pw){
  if(!crypto.subtle) throw new Error("browser");
  const mat = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw.normalize("NFC")), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey({name:"PBKDF2", salt:b64(P.salt), iterations:P.iter, hash:"SHA-256"},
    mat, {name:"AES-GCM", length:256}, false, ["decrypt"]);
  const buf = await crypto.subtle.decrypt({name:"AES-GCM", iv:b64(P.iv)}, key, b64(P.ct));
  return new TextDecoder().decode(buf);
}
function apri(html){document.open();document.write(html);document.close();}
async function prova(pw, ricorda){
  const html = await decifra(pw);
  if(ricorda){try{sessionStorage.setItem(KEY, pw)}catch(e){}}
  apri(html);
}
document.getElementById("gate").addEventListener("submit", async e => {
  e.preventDefault(); messaggio(""); go.disabled = true;
  try{ await prova(document.getElementById("pw").value.trim(), true); }
  catch(x){ go.disabled = false; messaggio(x.message === "browser" ? "Questo browser non supporta la pagina: apri con Chrome, Safari o Firefox aggiornati." : "Password sbagliata."); }
});
(async () => {
  let pw = null; try{ pw = sessionStorage.getItem(KEY) }catch(e){}
  if(!pw) return;
  try{ await prova(pw, false) }
  catch(x){ try{sessionStorage.removeItem(KEY)}catch(e){} document.documentElement.classList.remove("riapre"); }
})();
</script>
</body></html>
"""


def cifra(testo, pw):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERAZIONI).derive(pw.encode())
    ct = AESGCM(key).encrypt(iv, testo.encode(), None)
    e = lambda b: base64.b64encode(b).decode()
    return {"salt": e(salt), "iv": e(iv), "ct": e(ct), "iter": ITERAZIONI}


def main():
    import unicodedata
    pw = unicodedata.normalize("NFC", os.environ.get("RADAR_PASSWORD", "").strip())
    if not pw:
        sys.exit("manca RADAR_PASSWORD")
    fp = os.path.join(ROOT, "site", "index.html")
    html = open(fp, encoding="utf-8").read()
    if 'id="payload"' in html and "PBKDF2" in html:
        sys.exit("site/index.html e' gia' cifrata: rilancia build_site.py prima")
    cli = json.load(open(os.path.join(ROOT, "competitors.json"))).get("cliente") or {}
    ing = cli.get("ingresso") or {}
    titolo = cli.get("titolo") or cli.get("brand") or "Radar ads"
    logo = ""
    if ing.get("logo"):
        svg = open(os.path.join(ROOT, ing["logo"]), "rb").read()
        logo = f'<img class="logo" alt="{cli.get("brand", "")}" src="data:image/svg+xml;base64,{base64.b64encode(svg).decode()}">'
    font = ing.get("font") or ""
    famiglia = (f'"{font}",' if font else "") + 'ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif'
    link_font = (f'<link href="https://fonts.googleapis.com/css2?family={font.replace(" ", "+")}:wght@400;600&display=swap" rel="stylesheet">'
                 if font else "")
    payload = json.dumps(cifra(html, pw)).replace("</", "<\\/")
    out = SHELL
    for k, v in {"__TITOLO__": titolo, "__FONT__": link_font, "__FAMIGLIA__": famiglia, "__LOGO__": logo,
                 "__CHIAVE__": "radar-pw-" + (cli.get("dominio") or "x"),
                 "__BG__": ing.get("bg", "#f6f6f4"), "__CARD__": ing.get("card", "#ffffff"),
                 "__INK__": ing.get("ink", "#15150f"), "__MUTED__": ing.get("muted", "#6b6b60"),
                 "__LINE__": ing.get("line", "#e3e3dc"), "__ACCENT__": ing.get("accent", "#1a5f4a"),
                 "__PAYLOAD__": payload}.items():
        out = out.replace(k, v)
    open(fp, "w", encoding="utf-8").write(out)
    print(f"site/index.html cifrata ({len(html) // 1024} KB in chiaro, {len(out) // 1024} KB pubblicati)")


if __name__ == "__main__":
    main()
