# 12 – Sécurité

Approche **défense en profondeur** : chaque couche est protégée indépendamment.

## 1. Authentification et autorisation (API)
| Mesure | Implémentation | Fichier |
|---|---|---|
| Mots de passe hachés | **bcrypt**, sel aléatoire, coût 12 – jamais stockés en clair | `security.py` |
| Politique de mot de passe | ≥ 8 caractères, lettre + chiffre (Pydantic) | `routers/auth.py` |
| Authentification sans état | **JWT HS256** (claims `sub`, `role`, `iat`, `exp`, `iss`), expiration 2 h, secret ≥ 32 caractères aléatoires | `security.py` |
| Autorisation | **RBAC** : `viewer` < `analyst` < `admin` (`require_role`) | `security.py` |
| Messages d'erreur neutres | « E-mail ou mot de passe incorrect » (pas d'énumération de comptes) | `routers/auth.py` |
| Anti brute-force | **rate limiting** SlowAPI : login 10/min, inscription 5/min, IA 15-30/min, global 300/min | `limiter.py` |
| Service à service | Airflow → API via jeton partagé comparé en **temps constant** (`secrets.compare_digest`) | `security.py` |
| Traçabilité | **journal d'audit** (connexions réussies / échouées, changement de rôle, matching CV) | `audit_logs` |

## 2. Protection des entrées / sorties
- Validation stricte de tous les paramètres (types, longueurs, regex, bornes) par Pydantic / FastAPI.
- **Anti-injection NoSQL** : aucun objet JSON utilisateur n'est passé à MongoDB ; texte libre échappé
  (`re.escape`) ; test automatisé (`{"$ne": null}` traité comme une chaîne).
- Erreurs 500 génériques, sans stacktrace.
- En-têtes HTTP : `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`, **CSP**, `Cache-Control: no-store` ; CORS limité aux origines du front.
- Front : jeton en `sessionStorage`, `noopener noreferrer`, CSP nginx, pas de `dangerouslySetInnerHTML`
  (descriptions affichées en texte brut → pas de XSS).

## 3. Infrastructure (Docker)
- **Secrets hors du code** : fichier `.env` (exclu de Git), `.env.example` sans valeur réelle ;
  chaque service ne reçoit que **ses** variables (pas d'`env_file` global).
- **Réseaux séparés** : `backend-net` (bases, Kafka, Airflow) / `frontend-net` (nginx ↔ API).
- Ports publiés sur **127.0.0.1** uniquement (rien d'exposé sur le réseau local).
- **Moindre privilège MongoDB** : `--auth`, un utilisateur par usage (pipeline, API, BI en lecture seule).
- Conteneur API exécuté en **utilisateur non-root** ; `server_tokens off` sur nginx.
- Airflow : clé **Fernet** (chiffrement des connexions), secret webserver, `expose_config=false`.
- MinIO : bucket **versionné**.

## 4. Données personnelles et conformité (RGPD / CGU)
| Principe | Mise en œuvre |
|---|---|
| Minimisation | seules les offres publiques sont collectées ; section « Contact » du scraping supprimée ; e-mails et téléphones **masqués** dans les descriptions (`[email]`, `[tel]`) |
| Limitation de conservation | rétention Kafka 7 jours ; CV du matching **jamais stocké** |
| Sécurité des comptes | bcrypt, JWT, audit |
| Respect des sources | robots.txt vérifié, débit limité, User-Agent identifié, API officielles privilégiées, **attribution + lien vers l'offre originale** (CGU Remotive / Jobicy), pas de republication |

## 5. Mise en production (perspectives)
HTTPS (Traefik / Let's Encrypt) + HSTS (ligne prête dans `nginx.conf`), gestionnaire de secrets
(Vault / Docker secrets), rotation des clés JWT, refresh tokens, MFA admin, Kafka SASL/TLS, scan
des images (Trivy), sauvegardes MongoDB / MinIO chiffrées.

## Vérifier (démo / captures pour le rapport)
- Swagger sans jeton → **401** ; viewer sur `/api/admin/users` → **403**.
- 11 tentatives de login en 1 min → **429**.
- Compass : `users.password_hash` commence par `$2b$` (bcrypt).
- Page Pipeline (admin) : journal d'audit.
