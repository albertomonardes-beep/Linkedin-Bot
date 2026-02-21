# Job Bot Chile → Telegram

Bot automatizado que busca empleos en portales chilenos, los filtra con IA (Claude Haiku) según tu CV y preferencias, y te envía los relevantes por Telegram. Corre gratis en GitHub Actions.

## Portales soportados

| Portal | Método |
|--------|--------|
| trabajando.cl | requests + BeautifulSoup |
| laborum.cl | requests + BeautifulSoup |
| cl.computrabajo.com | requests + BeautifulSoup |
| linkedin.com | Playwright (headless Chromium, sin login) |

---

## Setup (15 minutos)

### 1. Fork / clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/job-bot.git
cd job-bot
```

### 2. Editar tu CV y preferencias

**`profile/cv.md`** — Reemplaza el template con tu CV real (formato libre, markdown).

**`profile/preferences.yaml`** — Edita según tus necesidades:

```yaml
job_titles: ["Senior Software Engineer", "Tech Lead"]
keywords: ["Python", "Django"]
locations: ["Santiago", "Remoto"]
exclude_keywords: ["junior", "practicante"]
relevance_threshold: 7          # 1-10; solo notifica >= este valor
max_jobs_per_run: 50            # cap para controlar costo de API
max_pages_per_portal: 3
```

### 3. Crear el bot de Telegram

1. Abre Telegram y escribe a **@BotFather**
2. Envía `/newbot` → elige nombre y username → copia el **token**
3. Escribe a **@userinfobot** → copia tu **Chat ID**

### 4. Configurar secrets en GitHub

Ve a tu repositorio → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Valor |
|--------|-------|
| `ANTHROPIC_API_KEY` | Tu API key de [console.anthropic.com](https://console.anthropic.com) |
| `TELEGRAM_BOT_TOKEN` | Token de @BotFather |
| `TELEGRAM_CHAT_ID` | Tu chat ID de @userinfobot |
| `GH_PAT` | Personal Access Token (ver abajo) |
| `LINKEDIN_EMAIL` | *(opcional)* Tu email de LinkedIn |
| `LINKEDIN_PASSWORD` | *(opcional)* Tu contraseña de LinkedIn |

**Crear GH_PAT:**
1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Scopes necesarios: `repo` + `workflow`
3. Copia el token y agrégalo como secret `GH_PAT`

### 5. Activar GitHub Actions

El workflow corre automáticamente cada 3 horas en horario laboral chileno (lunes a viernes).

Para probar manualmente:
1. Ve a la pestaña **Actions** de tu repositorio
2. Selecciona **Job Search Bot**
3. Clic en **Run workflow**

---

## Ejecución local

```bash
# Instalar dependencias
pip install -r requirements.txt
python -m playwright install chromium

# Configurar variables de entorno
cp .env.example .env
# Edita .env con tus credenciales

# Correr
python main.py
```

---

## Cómo funciona

```
GitHub Actions (cron) → main.py
  ├── Scrapers (trabajando.cl, laborum.cl, computrabajo.cl, linkedin.com)
  │     └── JobListing[] (título, empresa, ubicación, descripción)
  ├── Storage (seen_jobs.json) → filtra duplicados
  ├── Matcher (Claude Haiku)
  │     ├── Pre-filtro: excluye keywords (gratis)
  │     └── Batch scoring 1-10 con tu CV y preferencias
  └── Notifier → Telegram (solo jobs con score >= umbral)
        └── Commit seen_jobs.json [skip ci]
```

**Formato del mensaje Telegram:**
```
🔍 Nuevo empleo relevante (Score: 9/10)
📋 *Senior Python Developer*
🏢 Empresa XYZ
📍 Santiago / Remoto
💡 _Match perfecto: Python + Django + stack buscado_

🔗 https://...
Portal: trabajando.cl
```

---

## Costos estimados

| Servicio | Costo |
|----------|-------|
| GitHub Actions | Gratis (~1,500/2,000 min/mes) |
| Claude Haiku | ~$3-4 USD/mes (5 runs/día × 14 jobs × 950 tokens) |
| Telegram | Gratis |
| Servidor | Ninguno |

---

## Validación de selectores CSS

Los scrapers usan selectores CSS para extraer datos del HTML. Los portales cambian su diseño periódicamente, por lo que los selectores pueden romperse.

**Cómo validar y actualizar selectores:**

1. Abre el portal en tu navegador
2. Haz clic derecho en el elemento que quieres extraer (título, empresa, etc.)
3. Selecciona **Inspeccionar** (DevTools)
4. Copia el selector CSS del elemento
5. Actualiza el selector en el scraper correspondiente

**Archivos de scrapers:**
- `scrapers/trabajando.py` — trabajando.cl
- `scrapers/laborum.py` — laborum.cl
- `scrapers/computrabajo.py` — cl.computrabajo.com
- `scrapers/linkedin.py` — linkedin.com

**Señales de que un scraper se rompió:**
- El portal aparece en el resumen de Telegram con `⚠️ error: ...`
- Aparece en los logs: `No cards found on page 1`
- El portal retorna 0 resultados consistentemente

**Herramienta de diagnóstico rápido:**
```python
import requests
from bs4 import BeautifulSoup
url = "https://www.trabajando.cl/trabajo/resultados?q=python&location=santiago&page=1"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(r.text, "lxml")
# Prueba distintos selectores:
print(soup.select("div.aviso-item"))
```

---

## Troubleshooting

**No llegan mensajes a Telegram:**
- Verifica que el bot haya iniciado una conversación contigo (envía `/start` al bot)
- Confirma que `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` son correctos
- Revisa los logs del workflow en GitHub Actions

**Error de autenticación Anthropic:**
- Verifica que `ANTHROPIC_API_KEY` esté correctamente configurado
- Confirma que la cuenta tiene crédito disponible

**LinkedIn retorna 0 resultados:**
- LinkedIn limita el acceso anónimo; esto es esperado ocasionalmente
- El bot continúa funcionando con los otros 3 portales

**El workflow no commitea seen_jobs.json:**
- Verifica que `GH_PAT` tenga los scopes `repo` y `workflow`
- Confirma que el token no haya expirado

---

## Estructura del proyecto

```
job-bot/
├── .github/workflows/job_search.yml   # Cron + commit-back
├── scrapers/
│   ├── base.py                        # JobListing dataclass + BaseScraper ABC
│   ├── trabajando.py
│   ├── laborum.py
│   ├── computrabajo.py
│   └── linkedin.py
├── core/
│   ├── storage.py                     # Deduplicación + expiración 30 días
│   ├── matcher.py                     # Claude Haiku scoring
│   └── notifier.py                    # Telegram Bot API
├── profile/
│   ├── cv.md                          # Tu CV (editar)
│   └── preferences.yaml              # Preferencias (editar)
├── main.py                            # Orquestador
├── requirements.txt
├── .env.example
└── seen_jobs.json                     # Auto-generado por el bot
```
