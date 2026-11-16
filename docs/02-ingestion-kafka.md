# 02 – Ingestion : Apache Kafka

**Outils** : Apache Kafka 3.9 (mode **KRaft**, sans ZooKeeper), client `confluent-kafka`, Kafka UI
**Code** : `pipeline/jobinsight/ingestion/producer.py`, `consumer.py` · **Service** : `kafka` (docker-compose)

## Rôle
Kafka est le tampon entre la collecte et le stockage (Livrable 1 §10.2 : fiabilité, rejeu,
scalabilité, traçabilité).

```
collect_arbeitnow ─┐
collect_jobicy    ─┤  produce()          ┌──────── topic jobs.raw (3 partitions, rétention 7 j) ────────┐
collect_remotive  ─┼──────────────────►  │ key = "<source>:<id>"   value = enveloppe JSON (gzip)       │
collect_pythonorg ─┘                     └───────────────────────────────────────────────┬──────────────┘
                                                                     consumer group "lake-writer"
                                                                                         ▼
                                                     MinIO raw/<source>/<date>/batch_<run>.jsonl
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
- Messages illisibles comptés (`invalid`) sans bloquer le lot.

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
```
