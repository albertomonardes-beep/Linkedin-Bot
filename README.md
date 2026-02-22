# Job Bot Chile → Telegram

Bot automatizado que busca empleos en portales chilenos, los filtra con IA (Claude Haiku) según tu CV y preferencias, y envía los relevantes por Telegram. Corre gratis en GitHub Actions.

## Portales soportados

| Portal | Método |
|--------|--------|
| trabajando.cl | requests + BeautifulSoup |
| laborum.cl | requests + BeautifulSoup |
| cl.computrabajo.com | requests + BeautifulSoup |
| linkedin.com | Playwright (headless Chromium, sin login) |

---

## Estado del setup

- [x] Código implementado y subido al repo
- [x] `profile/cv.md` — CV real cargado
- [x] `profile/preferences.yaml` — Preferencias configuradas
- [x] Secret `TELEGRAM_BOT_TOKEN` — configurado
- [x] Secret `TELEGRAM_CHAT_ID` — configurado
- [x] Secret `ANTHROPIC_API_KEY` — configurado
- [x] Secret `GH_PAT` — configurado
- [ ] Prueba local con `.env`
- [ ] Primer run en GitHub Actions

---

## Setup paso a paso

### Paso 1 — Crear el bot de Telegram y obtener los tokens

**1a. Crear el bot (obtener `TELEGRAM_BOT_TOKEN`):**
1. Abre Telegram y busca **@BotFather**
2. Escríbele `/newbot`
3. Te pedirá un nombre para mostrar (ej: `Job Bot Alberto`)
4. Te pedirá un username — debe terminar en `bot` (ej: `alberto_jobs_bot`)
5. Te responderá con un token como: `7123456789:AAF-xxxxxxxxxxxxxxxxxxxxxxxxxxx`
6. Copia ese token → es tu `TELEGRAM_BOT_TOKEN`

**1b. Obtener tu Chat ID (obtener `TELEGRAM_CHAT_ID`):**
1. Busca **@userinfobot** en Telegram
2. Escríbele cualquier mensaje
3. Te responderá con tu ID numérico (ej: `123456789`)
4. Copia ese número → es tu `TELEGRAM_CHAT_ID`

**1c. Iniciar conversación con tu bot:**
- Busca el bot que creaste por su username y escríbele `/start`
- Esto es obligatorio — sin este paso el bot no puede enviarte mensajes

---

### Paso 2 — Obtener la API key de Anthropic (`ANTHROPIC_API_KEY`)

1. Ve a [console.anthropic.com](https://console.anthropic.com)
2. Inicia sesión o crea una cuenta
3. Ve a **API Keys** → **Create Key**
4. Copia la key → es tu `ANTHROPIC_API_KEY`
5. Asegúrate de tener crédito cargado (mínimo $5 USD alcanza para meses)

---

### Paso 3 — Crear el Personal Access Token de GitHub (`GH_PAT`)

Este token le permite al bot commitear `seen_jobs.json` de vuelta al repo.

1. Ve a [github.com/settings/tokens](https://github.com/settings/tokens)
2. Clic en **Generate new token (classic)**
3. Ponle un nombre (ej: `job-bot-pat`)
4. Expiration: 90 días o sin expiración
5. Marca estos scopes:
   - [x] `repo` (todos los sub-scopes)
   - [x] `workflow`
6. Clic en **Generate token**
7. Copia el token (solo se muestra una vez) → es tu `GH_PAT`

---

### Paso 4 — Agregar los secrets en GitHub

1. Ve a: https://github.com/albertomonardes-beep/Linkedin-Bot/settings/secrets/actions
2. Por cada secret, clic en **New repository secret**, escribe el nombre exacto y pega el valor:

| Secret | Dónde lo obtuviste |
|--------|--------------------|
| `TELEGRAM_BOT_TOKEN` | @BotFather en Telegram |
| `TELEGRAM_CHAT_ID` | @userinfobot en Telegram |
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `GH_PAT` | github.com/settings/tokens |

---

### Paso 5 — Prueba local (opcional pero recomendada)

```bash
# Instalar dependencias
pip install -r requirements.txt
python -m playwright install chromium

# Configurar variables de entorno
cp .env.example .env
# Abre .env y llena los 4 valores con los mismos secrets del paso anterior

# Correr
python main.py
```

Si todo está bien, recibirás mensajes en Telegram y se creará/actualizará `seen_jobs.json`.

---

### Paso 6 — Ejecutar en GitHub Actions

El workflow corre automáticamente cada 3 horas en horario laboral chileno (lunes a viernes, 08:00–20:00 CLT).

Para probar manualmente:
1. Ve a la pestaña **Actions** del repositorio
2. Selecciona **Job Search Bot**
3. Clic en **Run workflow** → **Run workflow**
4. Espera ~5 minutos y revisa Telegram

---

## Cómo funciona

```
GitHub Actions (cron: cada 3h, L-V) → main.py
  │
  ├─ Scrapers: trabajando.cl, laborum.cl, computrabajo.cl, linkedin.com
  │     └── Busca los títulos de preferences.yaml en Santiago y Remoto
  │
  ├─ Storage: filtra URLs ya vistas en seen_jobs.json (TTL 30 días)
  │
  ├─ Matcher (Claude Haiku):
  │     ├── Pre-filtro: descarta keywords excluidas (gratis)
  │     └── Batch scoring 1-10 comparando con cv.md y preferences.yaml
  │
  ├─ Telegram: envía solo jobs con score >= 7
  │     └── Resumen al final con total encontrado/enviado por portal
  │
  └─ Git: commitea seen_jobs.json actualizado [skip ci]
```

**Formato del mensaje en Telegram:**
```
🔍 Nuevo empleo relevante (Score: 9/10)
📋 *Gerente de Operaciones*
🏢 Empresa XYZ
📍 Santiago
💡 _Coincide con supply chain + liderazgo de equipos grandes_

🔗 https://...
Portal: trabajando.cl
```

---

## Preferencias configuradas

Los cargos que busca el bot actualmente (`profile/preferences.yaml`):

- Gerente / Subgerente / Sub Gerente / Sub-Gerente de:
  - Operaciones
  - Logística
  - Supply Chain
  - Producción
  - Manufactura

**Excluye automáticamente:** junior, analista, coordinador, asistente, técnico, practicante, auxiliar, operario.

Para cambiar los cargos o keywords, edita `profile/preferences.yaml` y haz push.

---

## Costos estimados

| Servicio | Costo mensual |
|----------|--------------|
| GitHub Actions | Gratis (~1,500 / 2,000 min disponibles) |
| Claude Haiku | ~$3–4 USD (5 runs/día × ~14 jobs × ~950 tokens) |
| Telegram Bot API | Gratis |
| Servidor | $0 (sin servidor) |

---

## Validación de selectores CSS

Los scrapers usan selectores CSS para extraer datos del HTML. Los portales cambian su diseño periódicamente, por lo que los selectores pueden romperse.

**Cómo detectar un scraper roto:**
- El resumen de Telegram muestra `⚠️ error: ...` para ese portal
- Los logs del workflow muestran `No cards found on page 1`
- El portal retorna 0 resultados de forma consistente

**Cómo actualizar un selector:**
1. Abre el portal en el navegador
2. Clic derecho en el título/empresa → **Inspeccionar**
3. Copia el selector CSS
4. Actualiza el archivo del scraper correspondiente:
   - `scrapers/trabajando.py`
   - `scrapers/laborum.py`
   - `scrapers/computrabajo.py`
   - `scrapers/linkedin.py`

**Diagnóstico rápido:**
```python
import requests
from bs4 import BeautifulSoup
url = "https://www.trabajando.cl/trabajo/resultados?q=gerente+operaciones&location=santiago&page=1"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(r.text, "lxml")
print(soup.select("div.aviso-item"))  # ajusta el selector según el portal
```

---

## Troubleshooting

**No llegan mensajes a Telegram:**
- Asegúrate de haber escrito `/start` al bot en Telegram
- Verifica que `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` sean correctos
- Revisa los logs del workflow en la pestaña Actions

**Error de autenticación Anthropic:**
- Verifica que `ANTHROPIC_API_KEY` esté bien copiada (sin espacios)
- Confirma que la cuenta tiene crédito disponible en console.anthropic.com

**LinkedIn retorna 0 resultados:**
- LinkedIn limita el acceso anónimo; es esperado ocasionalmente
- El bot sigue funcionando con los otros 3 portales sin interrupciones

**El workflow no commitea seen_jobs.json:**
- Verifica que `GH_PAT` tenga los scopes `repo` y `workflow`
- Confirma que el token no haya expirado

---

## Estructura del proyecto

```
job-bot/
├── .github/workflows/job_search.yml   # Cron cada 3h + commit-back
├── scrapers/
│   ├── base.py                        # JobListing dataclass + BaseScraper ABC
│   ├── trabajando.py
│   ├── laborum.py
│   ├── computrabajo.py
│   └── linkedin.py
├── core/
│   ├── storage.py                     # Deduplicación JSON, TTL 30 días
│   ├── matcher.py                     # Claude Haiku scoring 1-10
│   └── notifier.py                    # Telegram Bot API
├── profile/
│   ├── cv.md                          # CV de Alberto Monardes
│   └── preferences.yaml              # Cargos y preferencias configurados
├── main.py                            # Orquestador
├── PLAN.md                            # Documento de diseño y arquitectura
├── requirements.txt
├── .env.example
└── seen_jobs.json                     # Actualizado automáticamente por el bot
```
