# 02 – Ingestion : Apache Kafka

**Outils** : Apache Kafka 3.9 (mode **KRaft**, sans ZooKeeper), client `confluent-kafka`, Kafka UI
**Code** : `pipeline/jobinsight/ingestion/producer.py`, `consumer.py` · **Service** : `kafka` (docker-compose)

## Rôle
Kafka est le tampon entre la collecte et le stockage (Livrable 1 §10.2 : fiabilité, rejeu,
scalabilité, traçabilité).

```
collect_arbeitnow ─┐                  conforme  ┌──── topic jobs.raw (3 partitions, rétention 7 j) ────┐
collect_jobicy    ─┤   contrat de    ─────────► │ key = "<source>:<id>"  value = enveloppe JSON (gzip)  │
collect_wttj      ─┼─► données       │          └──────────────────────────────────────┬───────────────┘
collect_...       ─┘   (producteur)  │ rejetée  ┌──── topic jobs.dlq (file de rejet) ──┐│
                                     └────────► │ offre d'origine + violations          ││
                                                └──────────────────────┬────────────────┘│
                                                     consumer group "lake-writer"       ▼
                                  MinIO dlq/<date>/batch_<run>.jsonl ◄─┘   MinIO raw/<source>/<date>/batch_<run>.jsonl
```

## Producteur – garanties
| Paramètre | Valeur | Effet |
|---|---|---|
| `enable.idempotence` | true | pas de doublon en cas de retry réseau |
| `acks` | all | message confirmé seulement une fois écrit |
| `compression.type` | gzip | descriptions volumineuses compressées |
| clé | `source:source_id` | une même offre va toujours dans la même partition (ordre garanti) |
| callback `on_delivery` | compte les erreurs | statut `partial` remonté au monitoring |

## Consommateur – mode batch
- Lit le topic jusqu'à 15 s sans nouveau message, regroupe par source.
- Écrit un fichier JSONL par source dans la zone Raw.
- **Commit des offsets après l'écriture réussie** → sémantique *at-least-once* : aucune perte ;
  un éventuel doublon est éliminé par la déduplication Spark / l'upsert MongoDB.
- Lit aussi la file de rejet `jobs.dlq` et l'écrit dans `dlq/` du Data Lake.
- Un message illisible dans `jobs.raw` n'est plus jeté : il rejoint la file de rejet avec le code
  `consumer.unreadable_message`, sans bloquer le lot.

## Contrat de données et file de rejet (DLQ)
**Code** : `pipeline/jobinsight/ingestion/contracts.py` · **Tests** : `pipeline/tests/test_contracts.py`

Chaque offre est vérifiée par le producteur **avant** d'entrer dans Kafka. Une offre non conforme
ne pollue pas la zone Raw : elle part dans le topic `jobs.dlq` avec la liste de ses violations,
puis dans `dlq/<date>/batch_<run>.jsonl`. Elle reste consultable et rejouable.

| Niveau | Règles | Exemples de codes |
|---|---|---|
| Enveloppe (commune) | source connue, type de source (`api`, `scraping`, `sitemap`), identifiant, lot, horodatage ISO, payload objet, taille de 4 Mo au plus | `envelope.source_unknown`, `envelope.too_large` |
| Payload (par source) | titre présent (300 caractères au plus), lien présent et en `http(s)`, types des champs numériques et listes | `payload.title_missing`, `payload.not_numeric:salaryMin` |

Le contrat vérifie que l'offre est **exploitable** (structure). La Data Quality de Spark vérifie
ensuite qu'elle est **plausible** (contenu). Les deux sont complémentaires.

**Monitoring** : chaque tâche `collect_<source>` enregistre `published`, `rejected`, `reject_rate`
et les violations les plus fréquentes (`reject_reasons`) dans `pipeline_runs`. Au-delà de 20 % de
rejets, la collecte de la source passe en statut `partial` (alerte).

**Calibrage sur les données réelles** : `scripts/profile_raw_fields.py` mesure le taux de
remplissage et le type de chaque champ dans la zone Raw. La première version du contrat, passée
sur les 6 302 offres du run du 20/11/2026, en rejetait 79 % : le type `sitemap` de WTTJ avait été
oublié et le seuil de taille (1 Mo) écartait de vraies offres Arbeitnow contenant une image de
2,4 Mo. Après correction : 0 % de rejet sur ce lot. Un test vérifie désormais que chaque
collecteur réel est couvert par le contrat.

**Bug corrigé au passage** : le mode fichier découpait les JSONL avec `splitlines()`, qui coupe
aussi sur les séparateurs Unicode (`U+2028`) présents dans certaines descriptions. Le découpage se
fait maintenant sur `\n` uniquement.

## Pourquoi Kafka plutôt qu'une écriture directe ?
- Découplage : la collecte fonctionne même si MinIO est indisponible (messages conservés 7 j).
- Rejeu : on peut relire le topic depuis un offset donné.
- Évolution vers le **streaming** : il suffirait d'un consommateur continu (ou Spark Structured
  Streaming) sans modifier les collecteurs.
- Plusieurs consommateurs possibles sur les mêmes données (ex. alerting temps réel).

## Mode développement sans Kafka
`INGESTION_MODE=file` : les enveloppes sont écrites dans `data/landing/` puis déplacées vers le
Data Lake – utile pour tester sans l'infrastructure complète.

## Observer
```bash
docker compose --profile admin up -d kafka-ui   # http://localhost:8081
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic jobs.raw --from-beginning --max-messages 1
# offres rejetées par le contrat
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic jobs.dlq --from-beginning --max-messages 5
```
