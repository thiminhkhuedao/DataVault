# DataVault SaaS — Spec-Driven Development
> Chaque feature est spécifiée avant d'être codée.
> Format : INPUT → PROCESSING → OUTPUT → ERRORS → TESTS

---

## Comment lire ce document

Chaque spec suit ce format :
```
ENDPOINT ou FONCTION
├── Input      : ce qui entre
├── Processing : ce qui se passe
├── Output     : ce qui sort
├── Errors     : cas d'erreur
└── Tests      : comment vérifier
```

---

# MODULE 1 — Auth & Users

## SPEC-001 : Créer un utilisateur via webhook Clerk

```
POST /api/webhooks/clerk

INPUT:
  Headers:
    svix-id: string
    svix-timestamp: string
    svix-signature: string
  Body (Clerk event):
    type: "user.created" | "user.updated" | "user.deleted"
    data:
      id: string          ← clerk_id
      email_addresses: [{email_address: string}]

PROCESSING:
  1. Vérifier signature webhook avec CLERK_WEBHOOK_SECRET
  2. Si type == "user.created":
     - Créer row dans users (clerk_id, email, plan="free")
  3. Si type == "user.updated":
     - Mettre à jour email si changé
  4. Si type == "user.deleted":
     - Soft delete (ne pas supprimer les données)

OUTPUT:
  200 { "status": "ok" }

ERRORS:
  400 { "error": "Invalid webhook signature" }
  500 { "error": "Database error" }

TESTS:
  ✓ Webhook valide crée un user en DB
  ✓ Webhook invalide (mauvaise signature) → 400
  ✓ user.deleted ne supprime pas les projets
  ✓ Double appel (idempotent) ne crée pas deux users
```

---

## SPEC-002 : Récupérer l'utilisateur courant

```
GET /api/me

INPUT:
  Headers:
    Authorization: Bearer <clerk_jwt>

PROCESSING:
  1. Vérifier JWT avec Clerk SDK
  2. Extraire clerk_id du JWT
  3. Récupérer user en DB par clerk_id

OUTPUT:
  200 {
    "id": "uuid",
    "email": "user@example.com",
    "plan": "free",
    "limits": {
      "projects": 3,
      "files_per_project": 5,
      "versions_per_file": 10
    },
    "usage": {
      "projects": 1,
      "total_files": 3,
      "total_versions": 12
    }
  }

ERRORS:
  401 { "error": "Unauthorized" }
  404 { "error": "User not found" }

TESTS:
  ✓ JWT valide → retourne user avec usage
  ✓ JWT expiré → 401
  ✓ User inexistant en DB → 404
```

---

# MODULE 2 — Projects

## SPEC-003 : Créer un projet

```
POST /api/projects

INPUT:
  Headers:
    Authorization: Bearer <clerk_jwt>
  Body:
    name: string (1-100 chars, unique par user)

PROCESSING:
  1. Auth → récupérer user
  2. Vérifier limite plan :
     - free : max 3 projets → compter projets existants
     - pro/team : illimité
  3. Vérifier nom unique pour cet user
  4. Créer projet en DB
  5. Logger dans audit_logs : action="project.created"

OUTPUT:
  201 {
    "id": "uuid",
    "name": "my-project",
    "created_at": "2026-10-14T10:00:00Z",
    "files_count": 0
  }

ERRORS:
  400 { "error": "Name is required" }
  400 { "error": "Name already exists" }
  402 { "error": "Plan limit reached", "limit": 3, "current": 3, "upgrade_url": "/billing" }
  401 { "error": "Unauthorized" }

TESTS:
  ✓ Crée projet avec nom valide
  ✓ Rejette nom vide
  ✓ Rejette nom dupliqué
  ✓ User free avec 3 projets → 402
  ✓ User pro avec 100 projets → succès
  ✓ Audit log créé
```

---

## SPEC-004 : Lister les projets

```
GET /api/projects?page=1&limit=20

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>
  Query:
    page: int (default 1)
    limit: int (default 20, max 100)

PROCESSING:
  1. Auth
  2. Récupérer projets de l'user avec pagination
  3. Pour chaque projet : compter fichiers et versions

OUTPUT:
  200 {
    "projects": [
      {
        "id": "uuid",
        "name": "my-project",
        "created_at": "...",
        "files_count": 3,
        "versions_count": 12,
        "last_activity": "2026-10-14T10:00:00Z"
      }
    ],
    "total": 2,
    "page": 1,
    "limit": 20
  }

ERRORS:
  401 Unauthorized

TESTS:
  ✓ Retourne seulement les projets de l'user
  ✓ Pagination correcte
  ✓ files_count et versions_count corrects
```

---

# MODULE 3 — Files (Tracked Files)

## SPEC-005 : Ajouter un fichier (add)

```
POST /api/projects/{project_id}/files

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>
  Form data:
    file: File (multipart upload)
    message: string

PROCESSING:
  1. Auth + vérifier que project_id appartient à l'user
  2. Vérifier limite plan (files_per_project)
  3. Vérifier que le filename n'est pas déjà tracké dans ce projet
  4. Calculer SHA-256 du fichier uploadé
  5. Upload fichier vers R2 : key = {project_id}/{file_id}/v1
  6. Créer tracked_file en DB
  7. Créer version v1 en DB :
     - version_id: "v1"
     - hash: SHA-256
     - message: message
     - size_bytes: taille fichier
     - storage_key: chemin R2
  8. Construire hash chain :
     - prev_chain_hash = "GENESIS"
     - chain_hash = SHA256(hash|GENESIS|v1|timestamp|author|message)
     - Stocker chain_hash dans version
  9. Si CSV : parser et stocker row snapshot
  10. Logger audit : action="file.added"

OUTPUT:
  201 {
    "file_id": "uuid",
    "filename": "training_data.csv",
    "version": {
      "version_id": "v1",
      "hash": "542c990c...",
      "chain_hash": "2036bd5d...",
      "message": "raw data from source",
      "size_bytes": 1024,
      "created_at": "..."
    }
  }

ERRORS:
  400 { "error": "No file provided" }
  400 { "error": "File already tracked" }
  402 { "error": "Plan limit reached" }
  403 { "error": "Project not found or access denied" }
  413 { "error": "File too large", "max_bytes": 104857600 }

TESTS:
  ✓ Upload CSV → file créé + version v1 + chain_hash
  ✓ Upload fichier déjà tracké → 400
  ✓ Upload dans projet d'un autre user → 403
  ✓ SHA-256 calculé correctement
  ✓ Row snapshot créé pour CSV
  ✓ chain_hash = SHA256(file_hash|GENESIS|v1|...)
```

---

## SPEC-006 : Commiter une nouvelle version (commit)

```
POST /api/files/{file_id}/versions

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>
  Form data:
    file: File
    message: string

PROCESSING:
  1. Auth + vérifier accès
  2. Vérifier limite (versions_per_file)
  3. Calculer SHA-256 du nouveau fichier
  4. Comparer avec hash de la dernière version
     - Si identique → erreur "no changes"
  5. Vérifier que la version n'est pas gelée (frozen)
  6. Déterminer nouveau version_id : "v{n+1}"
  7. Upload vers R2 : {project_id}/{file_id}/v{n+1}
  8. Créer version en DB
  9. Calculer chain_hash :
     - prev_chain_hash = chain_hash de la version précédente
     - chain_hash = SHA256(hash|prev|version_id|timestamp|author|message)
  10. Si CSV : stocker row snapshot
  11. Logger audit

OUTPUT:
  201 {
    "version": {
      "version_id": "v2",
      "hash": "abc123...",
      "prev_hash": "542c990c...",
      "chain_hash": "def456...",
      "prev_chain_hash": "2036bd5d...",
      "message": "...",
      "size_bytes": 1200,
      "created_at": "..."
    }
  }

ERRORS:
  400 { "error": "No changes detected — file is identical to last version" }
  400 { "error": "Version v3 is frozen. Unfreeze first." }
  402 Plan limit reached
  403 Access denied

TESTS:
  ✓ Commit normal → nouvelle version + chain_hash correct
  ✓ Commit sans changement → 400
  ✓ Commit sur version gelée → 400
  ✓ chain_hash inclut prev_chain_hash
  ✓ version_id = "v{n+1}" correct
```

---

## SPEC-007 : Vérifier l'intégrité (verify)

```
GET /api/files/{file_id}/verify

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>

PROCESSING:
  1. Auth + vérifier accès
  2. Récupérer dernière version en DB
  3. Télécharger fichier depuis R2
  4. Recalculer SHA-256
  5. Comparer avec hash stocké

OUTPUT:
  200 {
    "verified": true,
    "filename": "training_data.csv",
    "version_id": "v3",
    "stored_hash": "ed8df23f...",
    "computed_hash": "ed8df23f...",
    "last_commit": "2026-10-14T10:00:00Z",
    "author": "nguye",
    "message": "approved dataset"
  }

  ou si TAMPERED:
  200 {
    "verified": false,
    "filename": "training_data.csv",
    "stored_hash": "ed8df23f...",
    "computed_hash": "e83595c8...",
    "tampered_at": "2026-10-14T11:00:00Z"
  }

ERRORS:
  403 Access denied
  404 File not found

TESTS:
  ✓ Fichier intact → verified: true
  ✓ Fichier modifié sur R2 → verified: false
  ✓ Hash computed correspond exactement au fichier stocké
```

---

## SPEC-008 : Vérifier la chaîne (chain)

```
GET /api/files/{file_id}/chain

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>

PROCESSING:
  1. Auth
  2. Récupérer toutes les versions dans l'ordre
  3. Pour chaque version :
     - Recomputer chain_hash depuis zéro
     - Comparer avec chain_hash stocké
  4. Retourner résultat par version

OUTPUT:
  200 {
    "chain_valid": true,
    "filename": "training_data.csv",
    "versions": [
      {
        "version_id": "v1",
        "valid": true,
        "chain_hash": "2036bd5d...",
        "prev_chain_hash": "GENESIS",
        "timestamp": "...",
        "message": "..."
      },
      {
        "version_id": "v2",
        "valid": true,
        "chain_hash": "abc49ad4...",
        "prev_chain_hash": "2036bd5d..."
      }
    ]
  }

ERRORS:
  403 Access denied
  404 File not found

TESTS:
  ✓ Chaîne intacte → chain_valid: true, toutes versions valid: true
  ✓ Version modifiée en DB → chain_valid: false, version concernée valid: false
  ✓ Version supprimée → rupture de chaîne détectée
  ✓ Recompute correct : SHA256(hash|prev|vid|ts|author|msg)
```

---

# MODULE 4 — Signing

## SPEC-009 : Signer une version

```
POST /api/versions/{version_id}/sign

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>
  Body:
    role: "reviewer" | "approver" | "owner" | "witness"

PROCESSING:
  1. Auth → récupérer user (signer = user.email ou user.name)
  2. Vérifier que version_id existe et est accessible
  3. Vérifier rôle valide
  4. Vérifier pas déjà signé (même signer + même rôle)
  5. Récupérer file_hash de la version
  6. Calculer signature :
     signed_at = now()
     sig_input = f"{signer}|{role}|{file_hash}|{version_id}|{signed_at}"
     sig_hash = SHA256(sig_input)[:32]
  7. Stocker signature en DB

OUTPUT:
  201 {
    "signature": {
      "id": "uuid",
      "signer": "alice@example.com",
      "role": "reviewer",
      "sig_hash": "486ba36d...",
      "file_hash": "ed8df23f...",
      "signed_at": "2026-10-14T10:00:00Z"
    }
  }

ERRORS:
  400 { "error": "Invalid role" }
  400 { "error": "Already signed as reviewer" }
  403 Access denied
  404 Version not found

TESTS:
  ✓ Signature créée avec sig_hash correct
  ✓ Même user peut signer avec deux rôles différents
  ✓ Même user ne peut pas signer deux fois avec même rôle
  ✓ sig_hash = SHA256(signer|role|file_hash|version_id|signed_at)[:32]
```

---

## SPEC-010 : Statut d'approbation

```
GET /api/versions/{version_id}/approve

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>

PROCESSING:
  1. Auth
  2. Récupérer toutes les signatures de la version
  3. Pour chaque signature :
     - Recomputer sig_hash
     - Vérifier que file_hash correspond au hash actuel de la version
  4. Déterminer :
     - has_reviewer
     - has_approver
     - all_valid (aucune signature invalide)
     - approved = has_reviewer AND has_approver AND all_valid

OUTPUT:
  200 {
    "approved": true,
    "version_id": "v3",
    "has_reviewer": true,
    "has_approver": true,
    "signatures": [
      {
        "signer": "alice@example.com",
        "role": "reviewer",
        "valid": true,
        "signed_at": "..."
      },
      {
        "signer": "bob@example.com",
        "role": "approver",
        "valid": true,
        "signed_at": "..."
      }
    ],
    "missing": []
  }

ERRORS:
  403 Access denied
  404 Version not found

TESTS:
  ✓ reviewer + approver → approved: true
  ✓ reviewer seul → approved: false, missing: ["approver"]
  ✓ Signature avec file_hash incorrect → valid: false
  ✓ Signature avec sig_hash modifié → valid: false
```

---

# MODULE 5 — Audit

## SPEC-011 : Générer rapport audit EU AI Act

```
GET /api/projects/{project_id}/audit/{file_id}

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>
  Query:
    format: "html" | "json" (default "html")

PROCESSING:
  1. Auth + vérifier plan (audit_reports: true)
  2. Récupérer :
     - Métadonnées projet
     - Toutes les versions du fichier
     - Toutes les signatures
     - Résultat vérification chain
     - Statut fichier actuel (verified/tampered)
  3. Calculer overall_status :
     - chain_valid AND file_intact AND approved → PASSED
     - sinon → FAILED
  4. Générer rapport HTML (réutiliser audit.py existant)
  5. Logger audit : action="audit.generated"

OUTPUT (format=json):
  200 {
    "overall": "PASSED",
    "generated_at": "...",
    "file": "training_data.csv",
    "project": "my-project",
    "checks": {
      "chain_valid": true,
      "file_intact": true,
      "has_reviewer": true,
      "has_approver": true,
      "approved": true
    },
    "versions_count": 3,
    "signatures_count": 2,
    "eu_ai_act": {
      "article_10": "COMPLIANT",
      "article_12": "COMPLIANT",
      "article_13": "COMPLIANT"
    }
  }

OUTPUT (format=html):
  200 Content-Type: text/html
  ← rapport HTML complet (identique à audit.py local)

ERRORS:
  402 { "error": "Audit reports require Pro plan", "upgrade_url": "/billing" }
  403 Access denied
  404 File not found

TESTS:
  ✓ Plan free → 402
  ✓ Plan pro → rapport généré
  ✓ overall=PASSED seulement si tous les checks passent
  ✓ Rapport HTML valide et lisible
  ✓ Audit log enregistré
```

---

# MODULE 6 — Billing

## SPEC-012 : Créer une session de paiement Stripe

```
POST /api/billing/checkout

INPUT:
  Headers: Authorization: Bearer <clerk_jwt>
  Body:
    plan: "pro" | "team"
    interval: "monthly" | "yearly"

PROCESSING:
  1. Auth
  2. Récupérer ou créer Stripe Customer pour l'user
  3. Récupérer Price ID selon plan + interval
  4. Créer Stripe Checkout Session :
     - customer: stripe_customer_id
     - line_items: [{price: price_id, quantity: 1}]
     - mode: "subscription"
     - success_url: "https://datavault.dev/dashboard?upgraded=true"
     - cancel_url: "https://datavault.dev/billing"
     - metadata: {user_id: uuid}

OUTPUT:
  200 { "checkout_url": "https://checkout.stripe.com/..." }

ERRORS:
  400 { "error": "Invalid plan" }
  401 Unauthorized

TESTS:
  ✓ Session créée avec bon price_id
  ✓ metadata contient user_id
  ✓ redirect vers success_url après paiement
```

---

## SPEC-013 : Webhook Stripe — mise à jour plan

```
POST /api/webhooks/stripe

INPUT:
  Headers:
    stripe-signature: string
  Body: Stripe event

EVENTS À GÉRER:
  checkout.session.completed:
    → récupérer user_id depuis metadata
    → récupérer plan depuis price_id
    → mettre à jour users.plan en DB
    → mettre à jour users.stripe_customer

  customer.subscription.updated:
    → mettre à jour plan selon nouveau price_id

  customer.subscription.deleted:
    → remettre plan à "free"

PROCESSING:
  1. Vérifier signature Stripe
  2. Switch sur event.type
  3. Mettre à jour DB
  4. Logger audit

OUTPUT:
  200 { "status": "ok" }

ERRORS:
  400 Invalid signature

TESTS:
  ✓ checkout.completed → plan mis à jour
  ✓ subscription.deleted → plan remis à free
  ✓ Signature invalide → 400
  ✓ Idempotent (double webhook ne change rien)
```

---

# MODULE 7 — Limites et middleware

## SPEC-014 : Middleware de vérification des limites

```
FONCTION: check_plan_limit(user, resource, project_id=None)

INPUT:
  user: User object (avec plan)
  resource: "projects" | "files" | "versions" | "audit"
  project_id: UUID (pour files et versions)

PROCESSING:
  limits = PLAN_LIMITS[user.plan]

  Si resource == "projects":
    if limits["projects"] == -1: return True
    count = SELECT COUNT(*) FROM projects WHERE user_id = user.id
    return count < limits["projects"]

  Si resource == "files":
    if limits["files_per_project"] == -1: return True
    count = SELECT COUNT(*) FROM tracked_files WHERE project_id = project_id
    return count < limits["files_per_project"]

  Si resource == "versions":
    if limits["versions_per_file"] == -1: return True
    # récupérer file_id depuis project_id
    count = SELECT COUNT(*) FROM versions WHERE file_id = file_id
    return count < limits["versions_per_file"]

  Si resource == "audit":
    return limits["audit_reports"]

OUTPUT:
  True (autorisé) ou False (limite atteinte)

TESTS:
  ✓ free user avec 3 projets → False pour "projects"
  ✓ pro user avec 100 projets → True pour "projects"
  ✓ free user → False pour "audit"
  ✓ pro user → True pour "audit"
```

---

# MODULE 8 — Frontend specs

## SPEC-015 : Page Dashboard

```
ROUTE: /dashboard
AUTH: Clerk (redirect si non connecté)

COMPOSANTS:
  - Header avec nom user + plan badge
  - Bouton "New project"
  - Liste des projets (cards) :
    - Nom du projet
    - Nombre de fichiers
    - Nombre de versions
    - Dernière activité
    - Lien vers /project/{id}
  - Si plan free : banner "Upgrade to Pro"

DATA FETCHING:
  GET /api/projects → liste projets
  GET /api/me → user + plan + usage

STATES:
  loading: skeleton cards
  empty: "No projects yet — create your first"
  error: "Could not load projects"

TESTS:
  ✓ Affiche seulement projets de l'user
  ✓ Redirect vers /sign-in si non connecté
  ✓ Banner upgrade visible si plan free
```

---

## SPEC-016 : Page Project

```
ROUTE: /project/{id}
AUTH: Clerk

COMPOSANTS:
  - Nom du projet + date création
  - Upload zone (drag & drop ou click)
  - Liste des fichiers trackés :
    - Filename
    - Nombre de versions
    - Statut (✓ intact / ⚠ modified / ✗ missing)
    - Hash dernière version (tronqué)
    - Bouton "View history"
    - Bouton "Verify"
  - Bouton "Generate Audit Report" (Pro only)

DATA FETCHING:
  GET /api/projects/{id} → détail projet
  GET /api/projects/{id}/files → liste fichiers

ACTIONS:
  Upload fichier → POST /api/projects/{id}/files
  Verify → GET /api/files/{id}/verify
  Audit → GET /api/projects/{id}/audit/{file_id}

TESTS:
  ✓ Projet d'un autre user → redirect 403
  ✓ Upload → nouveau fichier apparaît dans liste
  ✓ Audit bouton grisé si plan free
```

---

## SPEC-017 : Page File History

```
ROUTE: /file/{id}
AUTH: Clerk

COMPOSANTS:
  - Filename + projet parent
  - Timeline des versions (du plus récent au plus ancien) :
    - Version ID (v1, v2...)
    - Timestamp
    - Auteur
    - Message
    - Hash (tronqué)
    - Chain status (✓ valid / ✗ broken)
    - Tags
    - Signatures
    - Bouton "Restore this version"
  - Panel "Chain verification" : 
    - CHAIN INTACT / BROKEN
    - Détail par version
  - Panel "Signatures" :
    - Liste des signataires par version
    - Approval status

DATA FETCHING:
  GET /api/files/{id}/versions → historique
  GET /api/files/{id}/chain → vérification chaîne
  GET /api/versions/{id}/approve → statut approbation

TESTS:
  ✓ Versions dans ordre anti-chronologique
  ✓ Chain broken visible clairement
  ✓ Restore crée une nouvelle version
```

---

# MODULE 9 — Corrections de fiabilité (ajoutées après revue)

## SPEC-018 : Ancrage externe de la chaîne de hash

```
PROBLÈME:
  La chaîne de hash est stockée dans NOTRE base de données.
  Nous (ou quelqu'un qui pirate la base) pourrions la réécrire.
  Un auditeur externe ne peut donc pas s'y fier à 100 %.

SOLUTION:
  Publier régulièrement le dernier chain_hash de chaque fichier
  à un endroit que nous ne contrôlons pas.

FONCTION: anchor_chain_heads()   (tâche planifiée, 1 fois par jour)

INPUT:
  Pour chaque tracked_file avec au moins une version :
    file_id, dernier chain_hash, nombre de versions

PROCESSING:
  1. Construire un arbre de Merkle des (file_id | chain_hash | n_versions)
  2. Calculer la racine du jour : merkle_root
  3. Obtenir un horodatage tiers de merkle_root :
     - Option A : serveur RFC 3161 (autorité d'horodatage publique)
     - Option B : publier merkle_root dans un dépôt GitHub public
       (le commit fournit un horodatage que nous ne contrôlons pas)
  4. Stocker dans la table anchors : date, merkle_root, preuve (token ou URL de commit)

OUTPUT:
  Ligne dans anchors + audit_log "anchor.created"

VÉRIFICATION (endpoint GET /api/files/{id}/anchor-proof):
  Retourne : chain_hash, chemin de Merkle, merkle_root, preuve externe
  Un auditeur peut recalculer la racine et la comparer à la preuve externe
  SANS nous faire confiance.

ERRORS:
  Serveur d'horodatage injoignable → réessayer, alerter, ne jamais bloquer les commits

TESTS:
  ✓ Même entrée → même merkle_root
  ✓ Modifier un chain_hash en base → racine recalculée différente de l'ancrage
  ✓ Chemin de Merkle vérifiable hors ligne
  ✓ Échec de l'horodatage n'empêche pas un commit
```

---

## SPEC-019 : Vraies signatures numériques (Ed25519)

```
PROBLÈME:
  sig_hash = SHA256(signer|role|file_hash|...) n'utilise aucune clé secrète.
  Quelqu'un qui peut écrire dans la base peut fabriquer une signature.
  Clerk garantit QUI est connecté, pas que la signature n'a pas été forgée après coup.

MVP (acceptable, à documenter honnêtement):
  Garder sig_hash + identité vérifiée par Clerk.
  Ne PAS prétendre que ce sont des signatures cryptographiques non répudiables.

V2:
  Chaque utilisateur possède une paire de clés Ed25519.
  - Clé publique : stockée en base
  - Clé privée : générée et gardée dans le navigateur de l'utilisateur
    (WebCrypto), jamais envoyée au serveur
  Signer = signer en local (signer|role|file_hash|version_id|signed_at),
  envoyer la signature au serveur, qui la vérifie avec la clé publique.

TESTS (V2):
  ✓ Signature valide vérifiée avec la clé publique
  ✓ Modifier role ou file_hash invalide la signature
  ✓ Le serveur ne possède jamais la clé privée
```

---

## SPEC-020 : Chiffrement côté SaaS (AES-GCM)

```
PROBLÈME:
  encrypt.py (CLI) utilise un flux de clés maison basé sur HMAC-SHA256.
  Ce n'est pas de l'AES et ce n'est pas audité.

RÈGLE:
  Le SaaS n'utilise JAMAIS encrypt.py.
  Il utilise la bibliothèque 'cryptography' :
    - AES-256-GCM (chiffrement authentifié)
    - Clé dérivée par scrypt ou Argon2 (pas PBKDF2 seul)
    - Nonce aléatoire de 12 octets par fichier, jamais réutilisé
  Le stockage R2 chiffre déjà au repos : le chiffrement par utilisateur
  est une option, pas la base.

TESTS:
  ✓ Aller-retour chiffrer/déchiffrer
  ✓ Un octet modifié dans le chiffré → déchiffrement refusé (tag GCM)
  ✓ Deux chiffrements du même fichier donnent des résultats différents (nonce)
```

---

# Ordre d'implémentation

```
SPRINT 1 — Foundation (2 semaines)
  SPEC-001 : Webhook Clerk (users)
  SPEC-002 : GET /me
  SPEC-003 : Créer projet
  SPEC-004 : Lister projets
  SPEC-014 : Middleware limites

SPRINT 2 — Core versioning (2 semaines)
  SPEC-005 : Add file (upload + hash + chain)
  SPEC-006 : Commit version
  SPEC-007 : Verify
  SPEC-008 : Chain verification
  SPEC-018 : Ancrage externe de la chaîne (avant tout lancement public)

SPRINT 3 — Signing & Audit (2 semaines)
  SPEC-009 : Signer une version (MVP, limites documentées — voir SPEC-019)
  SPEC-010 : Statut approbation
  SPEC-011 : Rapport audit EU AI Act

SPRINT 4 — Billing (1 semaine)
  SPEC-012 : Checkout Stripe
  SPEC-013 : Webhook Stripe

SPRINT 5 — Frontend (3 semaines)
  SPEC-015 : Dashboard
  SPEC-016 : Page Project
  SPEC-017 : File History

SPRINT 6 — Polish & Launch
  Tests end-to-end
  Documentation API
  Product Hunt launch
```

---

# Règles de développement

```
1. Chaque endpoint a des tests avant d'être codé
2. Jamais de logique métier dans les routers — tout dans core/
3. Toutes les erreurs retournent { "error": "message" }
4. Toujours vérifier appartenance ressource avant action
5. Toujours logger dans audit_logs les actions importantes
6. Limites vérifiées côté backend uniquement
7. SHA-256 calculé côté backend uniquement (jamais faire confiance au client)
8. Stripe webhooks toujours vérifiés avec signature
9. Clerk JWT toujours vérifié avec SDK officiel
10. R2 storage keys jamais exposés au frontend — passer par API
```
11. Ne jamais écrire de cryptographie maison dans le SaaS : bibliothèques standard uniquement
12. Ne jamais afficher une garantie (« non répudiable », « inviolable ») que le code ne tient pas

---

# Notes d'implémentation — Sprint 1 (écarts volontaires par rapport aux specs)

| Spec | Écart | Raison |
|---|---|---|
| SPEC-003 | Nom vide → **422** (au lieu de 400) | Validation Pydantic standard ; le corps reste `{"error": "Validation error", "details": [...]}` |
| SPEC-003/004 | Projet d'un autre user → **404** (au lieu de 403) | Ne pas révéler qu'un identifiant existe |
| SPEC-001/002 | L'utilisateur est aussi créé à la 1re requête authentifiée | Évite la course entre webhook et 1re requête ; l'e-mail est complété par le webhook (colonne `email` nullable) |
| SPEC-001 | Utilisateur supprimé → **403** sur toutes les routes | Soft delete : données conservées, accès coupé |
| Structure | Code dans `app/` (package) au lieu de fichiers à plat | Imports propres, `uvicorn app.main:app`, tests |
| Dates | Type `UTCDateTime` | SQLite perdait le fuseau : même date sérialisée différemment entre création et liste |
