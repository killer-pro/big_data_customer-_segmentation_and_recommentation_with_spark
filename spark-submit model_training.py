import os
import logging
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, when, count, sum, avg, min, max, countDistinct,
    datediff, lit, percentile_approx, collect_list, split,
    first, coalesce, desc, asc, create_map
)
from pyspark.sql.window import Window
from pyspark.ml.recommendation import ALS
from pyspark.ml.clustering import KMeans
from pyspark.ml.feature import StringIndexer, VectorAssembler, StandardScaler
from pyspark.ml import Pipeline
from pyspark.ml.evaluation import ClusteringEvaluator, RegressionEvaluator
from pyspark.sql.types import DoubleType
from itertools import chain
import traceback
import re

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("model_training.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class EcommerceModelTrainer:
    def __init__(self, models_output_path="./models"):
        self.models_path = models_output_path
        self.spark = self._create_spark_session()
        os.makedirs(self.models_path, exist_ok=True)

    def _create_spark_session(self):
        """Crée la session Spark pour l'entraînement des modèles"""
        return SparkSession.builder \
            .appName("E-commerce Model Training") \
            .config("spark.driver.memory", "8g") \
            .config("spark.executor.memory", "8g") \
            .config("spark.sql.adaptive.enabled", "true") \
            .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
            .master("local[*]") \
            .getOrCreate()

    def prepare_user_features(self, cleaned_df):
        """Prépare les caractéristiques utilisateur pour la segmentation RFM et clustering"""
        logger.info("Préparation des caractéristiques utilisateur...")

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
            sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("purchases"),
            sum(when(col("event_type") == "remove_from_cart", 1).otherwise(0)).alias("removes"),

            # Diversité des produits/catégories
            countDistinct("product_id").alias("unique_products"),
            countDistinct("category_code").alias("unique_categories"),
            countDistinct("brand").alias("unique_brands"),

            # Prix moyen
            avg("price").alias("avg_price"),

            # Sessions
            countDistinct("user_session").alias("unique_sessions"),

            # Durée d'engagement
            (datediff(max("event_time"), min("event_time")) + 1).alias("engagement_days")
        )

        # Calcul des taux de conversion
        user_features = user_features.withColumn(
            "conversion_rate",
            when(col("views") > 0, col("purchases") / col("views")).otherwise(0)
        ).withColumn(
            "cart_abandonment",
            when(col("carts") > 0, (col("carts") - col("purchases")) / col("carts")).otherwise(0)
        ).withColumn(
            "avg_events_per_session",
            when(col("unique_sessions") > 0, col("total_events") / col("unique_sessions")).otherwise(0)
        )

        # Calcul du score RFM composite
        user_features = user_features.withColumn(
            "rfm_score",
            (100 - col("recency")) * 0.3 +
            col("frequency") * 0.3 +
            (col("monetary") / 100) * 0.4  # Normalisation simple du monetary
        )

        logger.info(f"Caractéristiques utilisateur préparées pour {user_features.count()} utilisateurs")
        return user_features

    def train_user_segmentation_model(self, user_features):
        """Entraîne le modèle de segmentation K-means"""
        logger.info("Entraînement du modèle de segmentation utilisateur...")

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

        # Entraînement
        model = pipeline.fit(user_features)

        # Prédictions
        segmented_users = model.transform(user_features)

        # Évaluation du clustering
        evaluator = ClusteringEvaluator(
            featuresCol="features",
            predictionCol="segment_id",
            metricName="silhouette"
        )
        silhouette_score = evaluator.evaluate(segmented_users)
        logger.info(f"Score de silhouette du clustering: {silhouette_score:.3f}")

        # Attribution de noms aux segments basés sur les caractéristiques
        segmented_users = self._assign_segment_names(segmented_users)

        # Sauvegarde du modèle
        model_path = os.path.join(self.models_path, "kmeans_model")
        model.write().overwrite().save(model_path)
        logger.info(f"Modèle K-means sauvegardé: {model_path}")

        # Sauvegarde des segments utilisateur
        segments_path = os.path.join(self.models_path, "user_segments.parquet")
        segmented_users.select(
            "user_id", "segment_id", "segment", "rfm_score",
            "recency", "frequency", "monetary", "conversion_rate"
        ).write.mode("overwrite").parquet(segments_path)
        logger.info(f"Segments utilisateur sauvegardés: {segments_path}")

        return model, segmented_users

    def _assign_segment_names(self, segmented_users):
        """Assigne des noms descriptifs aux segments basés sur leurs caractéristiques"""

        # Calcul des moyennes par segment
        segment_stats = segmented_users.groupBy("segment_id").agg(
            avg("recency").alias("avg_recency"),
            avg("frequency").alias("avg_frequency"),
            avg("monetary").alias("avg_monetary"),
            avg("conversion_rate").alias("avg_conversion"),
            count("*").alias("segment_size")
        ).collect()

        # Dictionnaire de mapping des segments
        segment_mapping = {}

        for row in segment_stats:
            segment_id = row.segment_id
            recency = row.avg_recency
            frequency = row.avg_frequency
            monetary = row.avg_monetary
            conversion = row.avg_conversion

            # Logique de nommage basée sur les caractéristiques RFM
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

            segment_mapping[segment_id] = segment_name
            logger.info(f"Segment {segment_id} ({segment_name}): "
                        f"Recency={recency:.1f}, Frequency={frequency:.1f}, "
                        f"Monetary={monetary:.1f}, Size={row.segment_size}")

        # Application du mapping en une seule opération
        mapping_expr = create_map([lit(x) for x in chain.from_iterable(segment_mapping.items())])
        segmented_users = segmented_users.withColumn(
            "segment",
            mapping_expr[col("segment_id")]
        )

        return segmented_users

    def prepare_product_features(self, cleaned_df):
        """Prépare les caractéristiques produit pour le système de recommandation"""
        logger.info("Préparation des caractéristiques produit...")

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

        logger.info(f"Caractéristiques produit préparées pour {product_features.count()} produits")
        return product_features

    def prepare_recommendation_data(self, cleaned_df):
        """Prépare les données pour le système de recommandation ALS"""
        logger.info("Préparation des données de recommandation...")

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

        # Sauvegarde du pipeline d'indexation
        indexer_path = os.path.join(self.models_path, "indexer_pipeline")
        indexer_model.write().overwrite().save(indexer_path)
        logger.info(f"Pipeline d'indexation sauvegardé: {indexer_path}")

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

        logger.info(f"Données d'interaction préparées: {interaction_data.count()} interactions")

        # Les caractéristiques produits seront chargées dans train_all_models

        # Sauvegarde des caractéristiques produits (cette étape sera déplacée ou modifiée)
        # features_path = os.path.join(self.models_path, "product_features.parquet")
        # product_features.write.mode("overwrite").parquet(features_path)
        # logger.info(f"Caractéristiques produits sauvegardées: {features_path}")

        # Retourner indexer_model pour l'utiliser dans le reste du training
        return interaction_data, indexer_model

    def train_als_model(self, interaction_data):
        """Entraîne le modèle de recommendation ALS"""
        logger.info("Entraînement du modèle ALS...")

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
        logger.info(f"RMSE du modèle ALS: {rmse:.3f}")

        # Sauvegarde du modèle
        als_path = os.path.join(self.models_path, "als_model")
        als_model.write().overwrite().save(als_path)
        logger.info(f"Modèle ALS sauvegardé: {als_path}")

        # Génération de recommandations pour tous les utilisateurs (cache)
        all_users = interaction_data.select("user_idx").distinct()
        user_recommendations = als_model.recommendForUserSubset(all_users, 10)

        # Sauvegarde des recommandations pré-calculées
        recs_path = os.path.join(self.models_path, "user_recommendations.parquet")
        user_recommendations.write.mode("overwrite").parquet(recs_path)
        logger.info(f"Recommandations utilisateur sauvegardées: {recs_path}")

        return als_model

    def _find_latest_parquet_file(self, directory_path, prefix):
        """Trouve le chemin du fichier parquet le plus récent avec un préfixe donné."""
        full_directory_path = os.path.abspath(directory_path).replace("\\", "/")
        latest_file = None
        latest_timestamp = None
        try:
            entries = os.listdir(full_directory_path)
            # Filtrer les entrées qui sont des répertoires et qui commencent par le préfixe
            matching_entries = [entry for entry in entries if os.path.isdir(os.path.join(full_directory_path, entry)) and entry.startswith(prefix)]

            for entry_name in matching_entries:
                entry_path = os.path.join(full_directory_path, entry_name)
                # Extraire le timestamp du nom du répertoire (format YYYYMMDD_HHMMSS)
                try:
                    # Trouver la partie timestamp YYYYMMDD_HHMMSS dans le nom du répertoire
                    timestamp_match = re.search(r'\d{8}_\d{6}', entry_name)
                    if timestamp_match:
                        timestamp_str = timestamp_match.group(0)
                        timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                        if latest_timestamp is None or timestamp > latest_timestamp:
                            latest_timestamp = timestamp
                            latest_file = entry_path # Le chemin du répertoire
                except Exception as ts_e:
                    logger.warning(f"Could not parse timestamp from {entry_name}: {ts_e}")
                    continue # Passer à l'entrée suivante si le timestamp est invalide

        except Exception as e:
            logger.error(f"Erreur lors de la recherche du fichier {prefix} dans {directory_path}: {e}")

        if latest_file:
            logger.info(f"Fichier (ou répertoire) le plus récent trouvé pour {prefix}: {latest_file}")
        else:
            logger.warning(f"Aucun fichier (ou répertoire) trouvé avec le préfixe {prefix} dans {directory_path}")

        return latest_file

    def train_all_models(self, cleaned_data_path, processed_data_path="./data/processed/parquet/"):
        """Entraîne tous les modèles nécessaires au système de recommandation"

        Args:
            cleaned_data_path (str): Chemin vers les données nettoyées (parquet).
            processed_data_path (str): Chemin vers le répertoire des données prétraitées (parquet).
        """
        logger.info("Début de l'entraînement de tous les modèles...")

        # Chargement des données nettoyées (toujours nécessaire pour l'indexation)
        logger.info(f"Chargement des données nettoyées depuis: {cleaned_data_path}")
        try:
            cleaned_df = self.spark.read.parquet(cleaned_data_path)
            logger.info(f"Données nettoyées chargées: {cleaned_df.count()} lignes")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des données nettoyées: {e}")
            return

        # 1. Chargement (ou préparation si fichiers manquants) des caractéristiques utilisateur
        user_behavior_path = self._find_latest_parquet_file(processed_data_path, "user_behavior_")
        if user_behavior_path:
            logger.info(f"Chargement des comportements utilisateur depuis: {user_behavior_path}")
            try:
                user_features = self.spark.read.parquet(user_behavior_path)
                logger.info(f"Comportements utilisateur chargés: {user_features.count()} utilisateurs")
            except Exception as e:
                logger.error(f"Erreur lors du chargement des comportements utilisateur: {e}")
                # Fallback vers la préparation si le chargement échoue
                logger.info("Fallback: Préparation des caractéristiques utilisateur depuis cleaned_df")
                user_features = self.prepare_user_features(cleaned_df)
        else:
            # Fallback si aucun fichier trouvé
            logger.warning("Aucun fichier de comportements utilisateur trouvé. Préparation depuis cleaned_df")
            user_features = self.prepare_user_features(cleaned_df)

        # 2. Entraînement du modèle de segmentation (utilise user_features)
        segmentation_model, segmented_users = self.train_user_segmentation_model(user_features)

        # 3. Préparation des données pour recommandation (Indexation)
        try:
            # prepare_recommendation_data va maintenant seulement faire l'indexation et les données d'interaction
            interaction_data, indexer_model = self.prepare_recommendation_data(cleaned_df)

             # Sauvegarde du pipeline d'indexation
            indexer_path = os.path.join(self.models_path, "indexer_pipeline")
            indexer_model.write().overwrite().save(indexer_path)
            logger.info(f"Pipeline d'indexation sauvegardé: {indexer_path}")

        except Exception as e:
            logger.error(f"Erreur lors de la préparation des données de recommandation (indexation): {e}")
            logger.error(traceback.format_exc())
            return # Arrêter si l'indexation échoue car ALS en dépend

        # 4. Chargement (ou préparation si fichiers manquants) des caractéristiques produits
        product_features_path = self._find_latest_parquet_file(processed_data_path, "product_data_")
        if product_features_path:
            logger.info(f"Chargement des caractéristiques produits depuis: {product_features_path}")
            try:
                # Le chargement des caractéristiques produits générées par analyse_praitraitement.py
                # doit correspondre au schéma attendu par le reste du pipeline.
                # Ici, on charge directement ce fichier au lieu de le recalculer.
                product_features = self.spark.read.parquet(product_features_path)
                logger.info(f"Caractéristiques produits chargées: {product_features.count()} produits")

                 # Sauvegarde des caractéristiques produits chargées dans le dossier des modèles pour cohérence
                features_path = os.path.join(self.models_path, "product_features.parquet")
                product_features.write.mode("overwrite").parquet(features_path)
                logger.info(f"Caractéristiques produits sauvegardées dans {self.models_path}: {features_path}")

            except Exception as e:
                logger.error(f"Erreur lors du chargement des caractéristiques produits: {e}")
                # Fallback vers la préparation si le chargement échoue
                logger.info("Fallback: Préparation des caractéristiques produits depuis cleaned_df")
                product_features = self.prepare_product_features(cleaned_df)
                 # Sauvegarde du fallback
                features_path = os.path.join(self.models_path, "product_features.parquet")
                product_features.write.mode("overwrite").parquet(features_path)
                logger.info(f"Fallback caractéristiques produits sauvegardées: {features_path}")

        else:
            # Fallback si aucun fichier trouvé
            logger.warning("Aucun fichier de caractéristiques produits trouvé. Préparation depuis cleaned_df")
            product_features = self.prepare_product_features(cleaned_df)
            # Sauvegarde du fallback
            features_path = os.path.join(self.models_path, "product_features.parquet")
            product_features.write.mode("overwrite").parquet(features_path)
            logger.info(f"Fallback caractéristiques produits sauvegardées: {features_path}")

        # 5. Entraînement du modèle ALS (utilise interaction_data)
        # S'assurer que l'ALS peut être entraîné avec interaction_data qui contient les IDs indexés
        if interaction_data is not None:
             als_model = self.train_als_model(interaction_data)
        else:
            logger.error("Les données d'interaction n'ont pas été préparées. Impossible d'entraîner le modèle ALS.")
            als_model = None # S'assurer que als_model est None en cas d'échec


        # 6. Sauvegarde des métadonnées du modèle
        metadata = {
            "training_date": datetime.now().isoformat(),
            "data_source": cleaned_data_path,
            "total_users": cleaned_df.select("user_id").distinct().count(),
            "total_products": cleaned_df.select("product_id").distinct().count(),
            "total_interactions": cleaned_df.count(),
            "segments_count": segmented_users.select("segment_id").distinct().count()
        }

        metadata_path = os.path.join(self.models_path, "model_metadata.json")
        with open(metadata_path, 'w') as f:
            import json
            json.dump(metadata, f, indent=2)

        return {
            "segmentation_model": segmentation_model,
            "als_model": als_model,
            "indexer_model": indexer_model,
            "metadata": metadata,
            "user_features": user_features, # Inclure pour référence si besoin
            "product_features": product_features # Inclure pour référence si besoin
        }

    def stop(self):
        """Arrête la session Spark"""
        self.spark.stop()


def main():
    """Fonction principale pour l'entraînement des modèles"""

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