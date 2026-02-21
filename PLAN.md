# Plan de Diseño — Job Bot Chile → Telegram

> Documento generado a partir de la conversación de diseño inicial (2026-02-21).
> Registra las decisiones de arquitectura, componentes y criterios usados para
> construir este proyecto.

---

## Contexto y motivación

Crear un sistema automatizado que:
1. Busca empleos en portales chilenos (trabajando.cl, laborum.cl, computrabajo.cl, LinkedIn)
2. Filtra los resultados con IA (Claude Haiku) comparándolos contra el CV y preferencias del usuario
3. Envía solo los relevantes por Telegram
4. Corre completamente gratis en GitHub Actions (sin servidor propio)

---

## Decisiones de arquitectura

### ¿Por qué GitHub Actions en vez de un servidor?
- 2,000 minutos/mes gratis en el plan Free
- El bot usa ~1,500 min/mes (cada 3h, lunes a viernes) → entra cómodo
- No requiere mantener ni pagar infraestructura
- El estado (seen_jobs.json) se persiste commiteándolo al propio repo con `[skip ci]`

### ¿Por qué Claude Haiku?
- Modelo más económico de la familia Claude; suficientemente capaz para scoring de empleos
- ~$3-4 USD/mes con el volumen esperado (5 runs/día × ~14 jobs nuevos × ~950 tokens)
- Permite batch scoring: una sola llamada API por lote de hasta 50 jobs

### ¿Por qué JSON para deduplicación en vez de una base de datos?
- Cero dependencias externas (no requiere Supabase, Redis, etc.)
- El archivo se commitea al repo → persiste entre runs de GitHub Actions
- Con expiración a 30 días el archivo no crece indefinidamente
- Escritura atómica (`os.replace`) para evitar corrupción

### ¿Por qué Playwright solo en LinkedIn?
- Los otros portales sirven HTML estático → requests + BS4 es suficiente y más rápido
- LinkedIn requiere JavaScript para renderizar los resultados
- Playwright se cachea en GitHub Actions para no reinstalar Chromium en cada run

---

## Estructura del proyecto

```
job-bot/
├── .github/workflows/job_search.yml   # Cron schedule + commit-back
├── scrapers/
│   ├── __init__.py
│   ├── base.py                        # BaseScraper + JobListing dataclass
│   ├── trabajando.py                  # trabajando.cl (requests + BS4)
│   ├── laborum.py                     # laborum.cl (requests + BS4)
│   ├── computrabajo.py                # cl.computrabajo.com (requests + BS4)
│   └── linkedin.py                    # LinkedIn Jobs (Playwright, anónimo)
├── core/
│   ├── matcher.py                     # Claude Haiku para scoring 1-10
│   ├── notifier.py                    # Telegram Bot API
│   └── storage.py                     # Deduplicación en seen_jobs.json
├── profile/
│   ├── cv.md                          # Usuario llena con su CV
│   └── preferences.yaml               # Títulos, keywords, ubicaciones
├── main.py                            # Orquestador principal
├── requirements.txt
├── .env.example
└── seen_jobs.json                     # Auto-generado, commiteado por el bot
```

---

## Flujo de datos

```
GitHub Actions (cron: cada 3h, L-V) → main.py
  │
  ├─ [1] Scrapers (paralelo conceptual, secuencial en código)
  │       ├── TrabajandoScraper  → JobListing[]
  │       ├── LaborumScraper     → JobListing[]
  │       ├── ComputrabajoScraper→ JobListing[]
  │       └── LinkedInScraper    → JobListing[]
  │              (Playwright headless, sin login, scroll lazy-load)
  │
  ├─ [2] Storage.new_jobs()
  │       └── Filtra URLs ya vistas en seen_jobs.json (con TTL 30 días)
  │
  ├─ [3] Matcher.filter_and_score()
  │       ├── Pre-filtro: excluye jobs con exclude_keywords (sin API)
  │       └── Claude Haiku: batch de hasta 50 jobs → score 1-10 + razón
  │
  ├─ [4] TelegramNotifier.send_job() para cada job con score >= threshold
  │
  ├─ [5] Storage.mark_seen() + Storage.save() (escritura atómica)
  │
  └─ [6] TelegramNotifier.send_summary() + git commit seen_jobs.json [skip ci]
```

---

## Componentes detallados

### BaseScraper (`scrapers/base.py`)

- **`JobListing`** dataclass: `url, title, company, location, portal, description, salary, score, score_reason`
- **`unique_id()`**: URL normalizada (sin trailing slash) como clave de deduplicación
- **`make_session()`**: Session con Retry (backoff exponencial en 429/500/502/503/504)
- **`random_delay(2–8s)`**: Evita rate limiting entre páginas
- **`search()`**: Itera todas las combinaciones keyword × location; falla silenciosamente por combo
- **`get_job_detail()`**: Opcional, para scrapers que necesiten la página de detalle

### URLs de búsqueda

| Portal | URL |
|--------|-----|
| trabajando.cl | `https://www.trabajando.cl/trabajo/resultados?q={kw}&location={loc}&page={n}` |
| laborum.cl | `https://www.laborum.cl/empleos?q={kw}&l={loc}&pg={n}` |
| computrabajo.cl | `https://cl.computrabajo.com/trabajo-de-{kw}-en-{loc}?p={n}` |
| linkedin.com | `https://www.linkedin.com/jobs/search?keywords={kw}&location={loc}&geoId=104621616` |

### Matcher IA (`core/matcher.py`)

**Fase 1 — pre-filtro (sin costo API):**
- Descarta jobs donde `title + description` contiene algún `exclude_keyword`

**Fase 2 — scoring en batch:**
- System prompt incluye el CV completo + preferencias
- User message: JSON array con hasta 50 jobs (título, empresa, ubicación, descripción truncada a 500 chars)
- Response esperada: JSON array `[{index, score, reason}, ...]`
- Tolerancia a markdown fences en la respuesta
- Fallback si falla el parse: score 0 para todos

**Criterios de scoring sugeridos al modelo:**
- 9-10: coincidencia muy alta (título + stack técnico + ubicación)
- 7-8: buena coincidencia (título o stack principal)
- 5-6: coincidencia parcial
- 1-4: poco relevante

### Storage (`core/storage.py`)

- Estructura en disco: `{"https://url...": <unix_timestamp_float>}`
- TTL: 30 días (86,400 × 30 segundos)
- Escritura atómica: escribe a `.tmp` → `os.replace()` al path final
- `new_jobs()`: filtro principal (O(n) lookup en dict de Python)
- `_prune()`: elimina entradas expiradas antes de cada save

### Notifier (`core/notifier.py`)

- Usa `parse_mode=Markdown` (Telegram v1)
- Escapa `* _ \` [ ` en campos libres (título, empresa)
- `send_summary()` al final de cada run con estado por portal (✅/⚠️)
- Delay de 0.5s entre mensajes (límite Telegram: 30 msg/s)

### GitHub Actions (`.github/workflows/job_search.yml`)

- Cron: `0 11,14,17,20,23 * * 1-5` (08:00, 11:00, 14:00, 17:00, 20:00 CLT)
- Cache Playwright: key = `playwright-chromium-{hash(requirements.txt)}`
- Commit-back: solo si `git diff --cached` detecta cambios
- `[skip ci]` en el mensaje del commit para evitar runs infinitos
- Requiere `GH_PAT` con scopes `repo` + `workflow`

---

## Configuración del usuario

**`profile/preferences.yaml`:**
```yaml
job_titles: ["Senior Software Engineer", "Tech Lead", "Backend Developer"]
keywords: ["Python", "Django", "React"]
locations: ["Santiago", "Remoto"]
exclude_keywords: ["junior", "trainee", "practicante"]
relevance_threshold: 7
max_jobs_per_run: 50
max_pages_per_portal: 3
```

**`profile/cv.md`:** CV completo del usuario en markdown (formato libre).

**Secrets de GitHub Actions:**
| Secret | Descripción |
|--------|-------------|
| `ANTHROPIC_API_KEY` | API key de Anthropic |
| `TELEGRAM_BOT_TOKEN` | Token del bot (vía @BotFather) |
| `TELEGRAM_CHAT_ID` | ID del chat destino |
| `GH_PAT` | Personal Access Token (scopes: repo, workflow) |
| `LINKEDIN_EMAIL` | *(opcional)* Para LinkedIn con login |
| `LINKEDIN_PASSWORD` | *(opcional)* Para LinkedIn con login |

---

## Estimación de costos

| Servicio | Costo mensual |
|----------|--------------|
| GitHub Actions | Gratis (~1,500 / 2,000 min disponibles) |
| Claude Haiku | ~$3–4 USD (5 runs/día × 14 jobs × 950 tokens) |
| Telegram Bot API | Gratis |
| Servidor | $0 (sin servidor) |

---

## Notas y limitaciones conocidas

- **Selectores CSS frágiles**: Los portales actualizan su HTML periódicamente. Ver guía de diagnóstico en README.md.
- **LinkedIn anónimo**: Máx ~25–75 resultados por keyword sin login. Suficiente para el caso de uso; no impacta los otros portales.
- **Fallo silencioso por diseño**: Si un portal falla, los demás continúan. El resumen de Telegram informa el estado de cada portal.
- **Primera ejecución**: Si seen_jobs.json está vacío, puede procesar muchos jobs de golpe. `max_jobs_per_run` evita costos excesivos de API.
- **Rate limiting**: Delays aleatorios de 2–8s entre páginas. LinkedIn usa Playwright que es naturalmente más lento.
