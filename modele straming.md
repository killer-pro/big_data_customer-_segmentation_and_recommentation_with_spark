# Entraînement des Modèles d'IA avec Apache Spark

## Vue d'ensemble

Cette section présente l'implémentation de l'entraînement des modèles d'intelligence artificielle pour le système de recommandation e-commerce utilisant Apache Spark. Le processus comprend deux composants principaux : un modèle de segmentation client basé sur l'approche RFM (Recency, Frequency, Monetary) et un système de recommandation collaborative utilisant l'algorithme ALS (Alternating Least Squares).

## Architecture du système d'entraînement

### Classe principale : EcommerceModelTrainer

Le système d'entraînement est encapsulé dans la classe `EcommerceModelTrainer` qui orchestre l'ensemble du processus. Cette classe centralise la gestion de la session Spark, la préparation des données et l'entraînement des modèles.

### Configuration Spark

La méthode `_create_spark_session()` initialise la session Spark avec une configuration optimisée :

```python
SparkSession.builder \
    .appName("E-commerce Model Training") \
    .config("spark.driver.memory", "8g") \
    .config("spark.executor.memory", "8g") \
    .config("spark.sql.adaptive.enabled", "true") \
    .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
    .master("local[*]")
```

Cette configuration alloue 8 Go de mémoire aux processus driver et executor, active l'optimisation adaptative des requêtes SQL et utilise la sérialisation Kryo pour améliorer les performances.

## Fonctions de préparation des données

### prepare_user_features()
**But** : Calculer les caractéristiques comportementales et RFM pour chaque utilisateur

Cette fonction transforme les données brutes d'événements en métriques utilisateur exploitables :

```python
# Calcul de la date de référence (date maximale dans les données)
max_date = cleaned_df.select(max("event_time")).first()[0]

# Calcul des métriques RFM et comportementales
user_features = cleaned_df.groupBy("user_id").agg(
    # Recency: nombre de jours depuis la dernière activité
    datediff(lit(max_date), max("event_time")).alias("recency"),
    
    # Frequency: nombre de jours distincts d'activité
    countDistinct(col("event_time").cast("date")).alias("frequency"),
    
    # Monetary: montant total des achats
    sum(when(col("event_type") == "purchase", col("price")).otherwise(0)).alias("monetary"),
    
    # Métriques comportementales
    count("*").alias("total_events"),
    sum(when(col("event_type") == "view", 1).otherwise(0)).alias("views"),
    sum(when(col("event_type") == "cart", 1).otherwise(0)).alias("carts"),
    sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("purchases")
)

# Calcul des taux de conversion
user_features = user_features.withColumn(
    "conversion_rate",
    when(col("views") > 0, col("purchases") / col("views")).otherwise(0)
).withColumn(
    "cart_abandonment",
    when(col("carts") > 0, (col("carts") - col("purchases")) / col("carts")).otherwise(0)
)
```

**Sortie** : DataFrame avec 15+ caractéristiques par utilisateur

### prepare_product_features()  
**But** : Agréger les métriques de performance et popularité par produit

Cette fonction analyse l'engagement des utilisateurs avec chaque produit :

```python
# Calcul des métriques agrégées par produit
product_features = cleaned_df.groupBy("product_id").agg(
    count("*").alias("total_events"),
    sum(when(col("event_type") == "view", 1).otherwise(0)).alias("total_views"),
    sum(when(col("event_type") == "cart", 1).otherwise(0)).alias("total_carts"),
    sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("total_purchases"),
    countDistinct("user_id").alias("unique_users"),
    avg("price").alias("avg_price"),
    first("category_code").alias("category_code"),
    first("brand").alias("brand")
)

# Nettoyage et extraction de la catégorie principale
product_features = product_features.withColumn(
    "category",
    when(col("category_code").isNull(), "unknown")
    .otherwise(split(col("category_code"), r"\\.")[0])
).drop("category_code")

# Calcul du score de popularité amélioré
product_features = product_features.withColumn(
    "enhanced_popularity_score",
    (col("total_purchases") * 3 + col("total_carts") * 2 + col("total_views")) / col("unique_users")
)
```

**Sortie** : DataFrame avec métriques d'engagement et métadonnées par produit

### prepare_recommendation_data()
**But** : Préparer et indexer les données pour l'algorithme ALS

Cette fonction transforme les données pour le système de recommandation :

```python
# Indexation des utilisateurs et produits
user_indexer = StringIndexer(
    inputCol="user_id",
    outputCol="user_idx",
    handleInvalid="keep"
)

product_indexer = StringIndexer(
    inputCol="product_id",
    outputCol="product_idx",
    handleInvalid="keep"
)

# Pipeline d'indexation
indexer_pipeline = Pipeline(stages=[user_indexer, product_indexer])
indexer_model = indexer_pipeline.fit(cleaned_df)
indexed_df = indexer_model.transform(cleaned_df)

# Préparation des données d'interaction avec scores implicites
interaction_data = indexed_df.filter(
    col("event_type").isin(["view", "cart", "purchase"])
).withColumn(
    "rating",
    when(col("event_type") == "view", 1.0)
    .when(col("event_type") == "cart", 3.0)
    .when(col("event_type") == "purchase", 5.0)
    .otherwise(0.0)
).groupBy("user_idx", "product_idx").agg(
    sum("rating").alias("rating"),
    count("*").alias("interaction_count")
).withColumn(
    "rating",
    # Normalisation du rating basée sur le nombre d'interactions
    when(col("rating") > 10, 10.0).otherwise(col("rating"))
)
```

**Sortie** : Données d'interaction indexées et pipeline de transformation

## Modèle de segmentation client (K-Means)

### Préparation des caractéristiques utilisateur

Le système calcule automatiquement les métriques RFM et comportementales pour chaque utilisateur :

- **Recency** : Nombre de jours depuis la dernière activité
- **Frequency** : Nombre de jours distincts d'activité 
- **Monetary** : Montant total des achats
- **Métriques comportementales** : Vues, ajouts au panier, achats, suppressions
- **Diversité** : Nombre de produits, catégories et marques uniques consultés
- **Taux de conversion** : Ratio achats/vues
- **Taux d'abandon panier** : Ratio (paniers - achats)/paniers

### train_user_segmentation_model()
**But** : Entraîner le modèle de clustering K-Means pour la segmentation client

Cette fonction implémente un pipeline complet de segmentation :

```python
# Sélection des caractéristiques pour le clustering
feature_cols = [
    "recency", "frequency", "monetary", "conversion_rate",
    "cart_abandonment", "unique_products", "unique_categories", "avg_price"
]

# Remplacement des valeurs nulles par 0
for col_name in feature_cols:
    user_features = user_features.withColumn(col_name,
                                           when(col(col_name).isNull(), 0.0).otherwise(
                                               col(col_name).cast(DoubleType())))

# Assemblage des caractéristiques
assembler = VectorAssembler(
    inputCols=feature_cols,
    outputCol="features_raw"
)

# Normalisation des caractéristiques
scaler = StandardScaler(
    inputCol="features_raw",
    outputCol="features",
    withStd=True,
    withMean=True
)

# Modèle K-means
kmeans = KMeans(
    featuresCol="features",
    predictionCol="segment_id",
    k=5,  # 5 segments utilisateur
    seed=42,
    maxIter=20
)

# Pipeline de preprocessing et clustering
pipeline = Pipeline(stages=[assembler, scaler, kmeans])
model = pipeline.fit(user_features)

# Évaluation du clustering
evaluator = ClusteringEvaluator(
    featuresCol="features",
    predictionCol="segment_id",
    metricName="silhouette"
)
silhouette_score = evaluator.evaluate(segmented_users)
```

**Sortie** : Modèle K-Means entraîné et utilisateurs segmentés avec noms descriptifs

### _assign_segment_names()
**But** : Attribuer automatiquement des noms métier aux segments numériques

Cette fonction utilitaire analyse les caractéristiques moyennes de chaque segment et applique une logique métier :

```python
# Calcul des moyennes par segment
segment_stats = segmented_users.groupBy("segment_id").agg(
    avg("recency").alias("avg_recency"),
    avg("frequency").alias("avg_frequency"),
    avg("monetary").alias("avg_monetary"),
    avg("conversion_rate").alias("avg_conversion"),
    count("*").alias("segment_size")
).collect()

# Logique de nommage basée sur les caractéristiques RFM
for row in segment_stats:
    segment_id = row.segment_id
    recency = row.avg_recency
    frequency = row.avg_frequency
    monetary = row.avg_monetary
    conversion = row.avg_conversion

    if monetary > 500 and frequency > 10 and recency < 30:
        segment_name = "VIP_Customers"
    elif frequency > 5 and recency < 60:
        segment_name = "Loyal_Customers"
    elif recency < 30 and conversion > 0.1:
        segment_name = "Active_Buyers"
    elif recency > 60 and frequency < 3:
        segment_name = "Dormant_Users"
    else:
        segment_name = "Casual_Browsers"

# Application du mapping
mapping_expr = create_map([lit(x) for x in chain.from_iterable(segment_mapping.items())])
segmented_users = segmented_users.withColumn(
    "segment",
    mapping_expr[col("segment_id")]
)
```

- **VIP_Customers** : Monetary > 500€, Frequency > 10 jours, Recency < 30 jours
- **Loyal_Customers** : Frequency > 5 jours, Recency < 60 jours  
- **Active_Buyers** : Recency < 30 jours, Conversion > 10%
- **Dormant_Users** : Recency > 60 jours, Frequency < 3 jours
- **Casual_Browsers** : Autres profils

### Évaluation du clustering

La qualité du clustering est mesurée par le score de silhouette, qui évalue la cohésion intra-cluster et la séparation inter-cluster.

## Système de recommandation collaborative (ALS)

### Préparation des données d'interaction

Le système transforme les événements utilisateur en scores d'interaction implicites :

- **Vues** : Score de 1.0
- **Ajouts au panier** : Score de 3.0  
- **Achats** : Score de 5.0

Les interactions multiples sont agrégées et normalisées avec un plafond à 10.0 pour éviter les biais.

### Indexation des entités

Un pipeline d'indexation convertit les identifiants string en indices numériques requis par ALS :

```python
user_indexer = StringIndexer(inputCol="user_id", outputCol="user_idx")
product_indexer = StringIndexer(inputCol="product_id", outputCol="product_idx")
```

### train_als_model()
**But** : Entraîner le modèle de recommandation collaborative ALS

Cette fonction implémente l'algorithme de factorisation matricielle :

```python
# Division train/test
train_data, test_data = interaction_data.randomSplit([0.8, 0.2], seed=42)

# Configuration du modèle ALS
als = ALS(
    userCol="user_idx",
    itemCol="product_idx",
    ratingCol="rating",
    nonnegative=True,
    implicitPrefs=True,  # Données implicites
    rank=50,  # Nombre de facteurs latents
    maxIter=15,  # Nombre d'itérations
    regParam=0.1,  # Régularisation
    alpha=1.0,  # Paramètre de confiance pour les données implicites
    coldStartStrategy="drop",
    seed=42
)

# Entraînement
als_model = als.fit(train_data)

# Évaluation sur les données de test
predictions = als_model.transform(test_data)
evaluator = RegressionEvaluator(
    metricName="rmse",
    labelCol="rating",
    predictionCol="prediction"
)
rmse = evaluator.evaluate(predictions.filter(col("prediction").isNotNull()))

# Génération de recommandations pour tous les utilisateurs (cache)
all_users = interaction_data.select("user_idx").distinct()
user_recommendations = als_model.recommendForUserSubset(all_users, 10)
```

**Sortie** : Modèle ALS entraîné et recommandations pré-calculées

## Fonctions utilitaires et de gestion

### _find_latest_parquet_file()
**But** : Identifier automatiquement le fichier de données le plus récent

Cette fonction utilitaire parcourt un répertoire pour trouver le fichier avec le timestamp le plus récent :

```python
def _find_latest_parquet_file(self, directory_path, prefix):
    full_directory_path = os.path.abspath(directory_path).replace("\\", "/")
    latest_file = None
    latest_timestamp = None
    
    try:
        entries = os.listdir(full_directory_path)
        # Filtrer les entrées qui sont des répertoires et qui commencent par le préfixe
        matching_entries = [entry for entry in entries 
                          if os.path.isdir(os.path.join(full_directory_path, entry)) 
                          and entry.startswith(prefix)]

        for entry_name in matching_entries:
            # Extraire le timestamp du nom du répertoire (format YYYYMMDD_HHMMSS)
            timestamp_match = re.search(r'\d{8}_\d{6}', entry_name)
            if timestamp_match:
                timestamp_str = timestamp_match.group(0)
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                if latest_timestamp is None or timestamp > latest_timestamp:
                    latest_timestamp = timestamp
                    latest_file = os.path.join(full_directory_path, entry_name)
    except Exception as e:
        logger.error(f"Erreur lors de la recherche du fichier {prefix}: {e}")
    
    return latest_file
```

**Utilité** : Permet la reprise automatique d'entraînement sur les données les plus fraîches

### train_all_models()
**But** : Orchestrer l'ensemble du processus d'entraînement

Cette fonction maîtresse coordonne tout le pipeline d'entraînement :

```python
def train_all_models(self, cleaned_data_path, processed_data_path="./data/processed/parquet/"):
    logger.info("Début de l'entraînement de tous les modèles...")

    # Chargement des données nettoyées
    cleaned_df = self.spark.read.parquet(cleaned_data_path)
    
    # 1. Chargement intelligent des caractéristiques utilisateur
    user_behavior_path = self._find_latest_parquet_file(processed_data_path, "user_behavior_")
    if user_behavior_path:
        user_features = self.spark.read.parquet(user_behavior_path)
    else:
        # Fallback vers la préparation si le fichier est manquant
        user_features = self.prepare_user_features(cleaned_df)

    # 2. Entraînement du modèle de segmentation
    segmentation_model, segmented_users = self.train_user_segmentation_model(user_features)

    # 3. Préparation des données pour recommandation (Indexation)
    interaction_data, indexer_model = self.prepare_recommendation_data(cleaned_df)

    # 4. Chargement des caractéristiques produits avec fallback
    product_features_path = self._find_latest_parquet_file(processed_data_path, "product_data_")
    if product_features_path:
        product_features = self.spark.read.parquet(product_features_path)
    else:
        product_features = self.prepare_product_features(cleaned_df)

    # 5. Entraînement du modèle ALS
    als_model = self.train_als_model(interaction_data)

    # 6. Sauvegarde des métadonnées
    metadata = {
        "training_date": datetime.now().isoformat(),
        "total_users": cleaned_df.select("user_id").distinct().count(),
        "total_products": cleaned_df.select("product_id").distinct().count(),
        "total_interactions": cleaned_df.count(),
        "segments_count": segmented_users.select("segment_id").distinct().count()
    }
```

**Flux d'exécution** :
```
Données nettoyées → Caractéristiques utilisateur → Segmentation K-Means
                 ↓
Indexation → Données d'interaction → Modèle ALS → Recommandations
                 ↓
Sauvegarde des modèles et métadonnées
```

**Sortie** : Dictionnaire contenant tous les modèles entraînés et leurs métadonnées

## Fonction principale et point d'entrée

### main()
**But** : Point d'entrée principal pour l'exécution via spark-submit

Cette fonction configure l'environnement d'exécution et lance le processus complet :

```python
def main():
    # Configuration des chemins
    CLEANED_DATA_PATH = "./data/processed/parquet/cleaned_data_*.parquet" 
    MODELS_OUTPUT_PATH = "./models"
    PROCESSED_DATA_PATH = "./data/processed/parquet/" 
    
    # Création du trainer
    trainer = EcommerceModelTrainer(models_output_path=MODELS_OUTPUT_PATH)

    try:
        # Entraînement de tous les modèles
        models = trainer.train_all_models(CLEANED_DATA_PATH, PROCESSED_DATA_PATH)
        logger.info("Tous les modèles ont été entraînés et sauvegardés avec succès!")

    except Exception as e:
        logger.error(f"Erreur lors de l'entraînement des modèles: {str(e)}")
        raise
    finally:
        trainer.stop()

if __name__ == "__main__":
    main()
```

**Usage** : `spark-submit model_training.py` pour lancement en production

### stop()
**But** : Fermer proprement la session Spark et libérer les ressources

```python
def stop(self):
    """Arrête la session Spark"""
    self.spark.stop()
```

Cette méthode garantit la libération correcte des ressources Spark, évitant les fuites mémoire et les processus orphelins.

## Gestion de la persistance et métadonnées

### Sauvegarde des modèles

Tous les modèles entraînés sont sauvegardés de manière persistante :

- **Modèle K-Means** : Pipeline complet incluant le préprocessing
- **Modèle ALS** : Modèle de factorisation matricielle
- **Pipeline d'indexation** : Mappings utilisateur/produit vers indices
- **Segments utilisateur** : Assignations de segments avec métriques RFM
- **Recommandations pré-calculées** : Top 10 recommandations par utilisateur

### Métadonnées d'entraînement

Le système sauvegarde automatiquement les métadonnées d'entraînement :

```json
{
  "training_date": "2024-12-XX",
  "total_users": 123456,
  "total_products": 7890,
  "total_interactions": 9876543,
  "segments_count": 5
}
```

## Optimisations et robustesse

### Gestion des données manquantes

Le système implémente plusieurs stratégies de robustesse :

- Remplacement des valeurs nulles par 0.0 dans les caractéristiques numériques
- Gestion des catégories manquantes avec une valeur "unknown"
- Stratégie "handleInvalid=keep" pour les nouveaux identifiants

### Chargement intelligent des données

La fonction `_find_latest_parquet_file()` identifie automatiquement les fichiers de données les plus récents basés sur des timestamps, permettant une reprise d'entraînement sur les données les plus à jour.

### Fallback automatique

En cas d'échec du chargement des données prétraitées, le système bascule automatiquement vers un calcul à partir des données nettoyées de base, assurant la continuité du processus d'entraînement.

## Métriques de performance

### Clustering
- **Score de silhouette** : Mesure la qualité de la séparation des segments
- **Distribution des segments** : Taille et caractéristiques moyennes par segment

### Recommandation
- **RMSE** : Erreur quadratique moyenne sur l'ensemble de test
- **Couverture** : Pourcentage de produits recommandés
- **Temps d'entraînement** : Performance du processus d'apprentissage

## Architecture de déploiement

Le système d'entraînement est conçu pour être exécuté via `spark-submit`, permettant une scalabilité horizontale sur un cluster Spark en production. La structure modulaire facilite la maintenance et l'extension avec de nouveaux algorithmes.