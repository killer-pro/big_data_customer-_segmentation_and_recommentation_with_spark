# Système de Recommandation en Temps Réel avec Spark Streaming

## Objectif

Cette section présente l'implémentation d'un système de recommandation capable de traiter des données clients en temps réel et de générer des recommandations instantanées. Le système utilise Apache Spark Structured Streaming pour consommer un flux de données d'interactions utilisateur-produit et applique un algorithme de recommandation hybride combinant filtrage collaboratif et popularité.

## Architecture du Streaming

### Configuration Spark
```python
def _create_spark_session(self):
    return SparkSession.builder \
        .appName("Streaming Recommendation System") \
        .config("spark.driver.memory", "8g") \
        .config("spark.executor.memory", "8g") \
        .config("spark.sql.streaming.checkpointLocation", "./checkpoint") \
        .master("local[*]") \
        .getOrCreate()
```

La session Spark est configurée avec :
- **Checkpointing** : Pour la tolérance aux pannes et la reprise après incident
- **Mémoire optimisée** : 8GB alloués au driver et aux executors pour traiter les données en mémoire
- **Mode local** : Utilisation de tous les cœurs disponibles

### Lecture du Flux de Données

```python
stream_df = self.spark.readStream \
    .format("csv") \
    .option("header", "true") \
    .schema(schema) \
    .option("maxFilesPerTrigger", 1) \
    .load(input_path)
```

**Points clés :**
- **Schéma défini** : Évite l'inférence automatique pour de meilleures performances
- **maxFilesPerTrigger** : Contrôle le débit de traitement (1 fichier par batch)
- **Format CSV** : Simulation de données temps réel à partir de fichiers

### Fenêtrage Temporel

```python
windowed_activity = stream_df \
    .withWatermark("event_time", "10 minutes") \
    .groupBy(
        window(col("event_time"), "5 minutes"),
        "user_id", "product_id", "event_type", "category_code", "brand", "price"
    ).agg(count("*").alias("event_count"))
```

**Mécanisme de fenêtrage :**
- **Watermark** : Tolère un retard maximum de 10 minutes pour les événements
- **Fenêtre glissante** : Agrégation sur des intervalles de 5 minutes
- **Agrégation** : Comptage des interactions par utilisateur/produit

## Algorithme de Recommandation

### Analyse des Interactions Utilisateur

```python
user_interactions = user_activity_df_processed.groupBy("user_id", "product_id") \
    .agg(
        count("*").alias("interaction_count"),
        spark_sum(when(col("event_type") == "view", 1).otherwise(0)).alias("views"),
        spark_sum(when(col("event_type") == "cart", 1).otherwise(0)).alias("carts"),
        spark_sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("purchases")
    )
```

**Agrégation des comportements :**
- Comptage total des interactions
- Distinction par type d'événement (vue, ajout panier, achat)
- Base pour le calcul des préférences utilisateur

### Extraction des Préférences Catégorielles

```python
user_categories = user_activity_df_processed.filter(col("category_code").isNotNull()) \
    .groupBy("user_id", "main_category") \
    .agg(count("*").alias("category_interest"))

top_categories = user_categories.withColumn(
    "rank", row_number().over(Window.partitionBy("user_id").orderBy(desc("category_interest")))
).filter(col("rank") <= 3)
```

**Identification des centres d'intérêt :**
- Extraction de la catégorie principale depuis le code complet
- Classement des catégories par fréquence d'interaction
- Sélection des 3 catégories les plus populaires par utilisateur

### Génération des Recommandations

```python
recommendations = top_categories.join(
    broadcast(self.product_popularity.filter(col("total_purchases") > 0)),
    on=top_categories.main_category == self.product_popularity.main_category_code, 
    how="inner"
).withColumn(
    "rec_score",
    col("category_interest") * col("total_purchases") / 100
).withColumn(
    "rank", row_number().over(Window.partitionBy("user_id").orderBy(desc("rec_score")))
)
```

**Algorithme hybride :**
- **Filtrage collaboratif** : Basé sur les préférences catégorielles de l'utilisateur
- **Popularité globale** : Pondération par le nombre total d'achats du produit
- **Score de recommandation** : Formule combinant intérêt personnel et popularité
- **Broadcast join** : Optimisation pour les données de référence (produits populaires)

### Mécanisme de Fallback

```python
if recommendations.isEmpty():
    logger.warning("Collaborative recommendations are empty. Falling back to popular products.")
    unique_users_df = user_activity_df_processed.select("user_id").distinct()
    top_popular_products = self.product_popularity
    
    fallback_recommendations = unique_users_df.crossJoin(top_popular_products.limit(10))
    recommendations = fallback_recommendations.select(
        col(unique_users_df.user_id).alias("user_id"),
        col(top_popular_products.product_id).alias("product_id"),
        lit(0.1).alias("rec_score"),
        col(top_popular_products.main_category_code).alias("recommended_category_code"),
        col(top_popular_products.main_brand).alias("main_brand"),
        col(top_popular_products.avg_price).alias("avg_price")
    ).withColumn("recommendation_type", lit("streaming_popular_fallback"))
```

**Stratégie de repli :**
- **Détection automatique** : Vérification si les recommandations collaboratives sont vides
- **Recommandations populaires** : Suggestion des 10 produits les plus vendus
- **Cross-join** : Attribution des mêmes produits populaires à tous les nouveaux utilisateurs

## Persistance et Monitoring

### Écriture vers InfluxDB

```python
def _write_to_influxdb(self, df, measurement_name):
    def write_batch(batch_df, batch_id):
        try:
            client = InfluxDBClient(url=INFLUXDB_CONFIG["url"], 
                                  token=INFLUXDB_CONFIG["token"])
            write_api = client.write_api(write_options=SYNCHRONOUS)
            
            points = []
            for row in batch_df.collect():
                point = Point(measurement_name)
                # Ajout des champs et tags selon le type de données
                points.append(point)
            
            write_api.write(bucket=INFLUXDB_CONFIG["bucket"], record=points)
        except Exception as e:
            logger.error(f"Error writing to InfluxDB: {e}")
```

**Monitoring temps réel :**
- **Métriques d'événements** : Suivi des interactions utilisateur
- **Métriques de recommandations** : Performance et qualité des suggestions
- **Base de données temporelle** : InfluxDB pour l'analyse des tendances

### Sauvegarde des Résultats

```python
# Sauvegarde incrémentale des recommandations
recommendations.write.mode("append").option("header", "true").csv(output_csv_path)
```

**Persistance des recommandations :**
- **Mode append** : Accumulation des résultats de chaque batch
- **Format CSV** : Facilite l'analyse post-traitement
- **Horodatage implicite** : Traçabilité temporelle des recommandations

## Configuration du Pipeline

### Traitement par Micro-Batch

```python
query = windowed_activity.writeStream \
    .outputMode("update") \
    .foreachBatch(process_batch) \
    .trigger(processingTime='60 seconds') \
    .start()
```

**Paramètres de streaming :**
- **Mode update** : Seules les lignes modifiées sont transmises
- **Trigger de 60 secondes** : Équilibre entre latence et throughput
- **ForeachBatch** : Traitement personnalisé de chaque micro-batch

### Gestion d'Erreurs et Tolérance aux Pannes

```python
try:
    query.awaitTermination()
except KeyboardInterrupt:
    logger.info("Stopping streaming...")
    query.stop()
    self.spark.stop()
```

**Robustesse du système :**
- **Arrêt gracieux** : Gestion des interruptions manuelles
- **Logging détaillé** : Traçabilité des erreurs et performances
- **Checkpointing automatique** : Reprise après panne

## Résultats et Performance

Le système traite les données en temps réel avec les caractéristiques suivantes :

- **Latence** : Recommandations générées en moins de 60 secondes après réception des données
- **Débit** : Capable de traiter des milliers d'interactions par batch
- **Scalabilité** : Architecture distribuée prête pour le passage à l'échelle
- **Qualité** : Algorithme hybride combinant personnalisation et popularité

Cette implémentation démontre la capacité de Spark Structured Streaming à alimenter des systèmes de recommandation temps réel, essentiels pour les applications e-commerce modernes nécessitant une personnalisation instantanée.