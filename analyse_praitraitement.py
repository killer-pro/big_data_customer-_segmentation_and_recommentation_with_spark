import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, when, month, dayofweek, hour, minute, second, dayofmonth, countDistinct,
    desc, sum, avg, min, max, datediff, lit, date_format,
    collect_list, split, coalesce, first, percentile_approx, approx_count_distinct, mode, expr
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, TimestampType, IntegerType, LongType, DecimalType
)
from pyspark.sql.window import Window
from datetime import datetime
import logging
from pyspark.ml.feature import StringIndexer
from pyspark.ml import Pipeline
# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("preprocessing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
input_file = "../data/2019-Oct_reduit.csv"
output_directory = "./data/processed"
os.makedirs(output_directory, exist_ok=True)
# Définition du schéma pour les données
schema = StructType([
    StructField("event_time", TimestampType(), True),
    StructField("event_type", StringType(), True),
    StructField("product_id", LongType(), True),
    StructField("category_id", DecimalType(38,0), True),
    StructField("category_code", StringType(), True),
    StructField("brand", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("user_id", StringType(), True),
    StructField("user_session", StringType(), True)
])

def create_spark_session():
    return SparkSession.builder \
        .appName("E-commerce Data Analysis") \
        .config("spark.driver.memory", "8g") \
        .config("spark.executor.memory", "8g") \
        .config("spark.sql.session.timeZone", "UTC") \
        .master("local[12]") \
        .getOrCreate()
def load_data(spark_session=None, input_path=input_file, schema=schema):
    if spark_session is None:
        spark_session = create_spark_session()
    logger.info(f"Chargement des données depuis {input_path}")
    try:
        df = spark_session.read.csv(
            input_path,
            header=True,
            schema=schema
        )
        logger.info(f"Données chargées : {df.count()} lignes")
        logger.info("Aperçu des données:")
        df.show(5)
        return df
    except Exception as e:
        logger.error(f"Erreur lors du chargement des données : {str(e)}")
        return None
def explore_data(df):
    if df is None:
        logger.error("Les données n'ont pas été chargées")
        return
    logger.info("Exploration initiale des données")
    logger.info(f"Nombre de lignes: {df.count()}")
    logger.info(f"Nombre de colonnes: {len(df.columns)}")

    logger.info("Schéma du DataFrame:")
    df.printSchema()
    logger.info("Statistiques descriptives:")
    df.describe().show()
    logger.info("Valeurs manquantes par colonne:")
    for column in df.columns:
        missing_count = df.filter(col(column).isNull()).count()
        missing_percentage = (missing_count / df.count()) * 100
        logger.info(f"{column}: {missing_count} ({missing_percentage:.2f}%)")
    logger.info("Distribution des types d'événements:")
    df.groupBy("event_type").count().orderBy(desc("count")).show()
    logger.info("Top 10 des catégories:")
    df.groupBy("category_code").count().orderBy(desc("count")).limit(10).show()
    logger.info("Top 10 des marques:")
    df.groupBy("brand").count().orderBy(desc("count")).limit(10).show()
    return df
def preprocess_data(df):
    if df is None:
        logger.error("Les données n'ont pas été chargées")
        return None
    logger.info("Prétraitement des données")
    # 1. Extraction des caractéristiques temporelles
    logger.info("Extraction des caractéristiques temporelles")
    df_temp = df.withColumn("hour", hour("event_time")) \
        .withColumn("minute", minute("event_time")) \
        .withColumn("second", second("event_time")) \
        .withColumn("day", dayofmonth("event_time")) \
        .withColumn("month", month("event_time")) \
        .withColumn("dayofweek", dayofweek("event_time")) \
        .withColumn("date", date_format("event_time", "yyyy-MM-dd")) \
        .withColumn("hour_bucket", date_format("event_time", "yyyy-MM-dd HH:00:00"))
    # 2. Traitement des valeurs manquantes
    logger.info("Traitement des valeurs manquantes")
    # Gestion des catégories hiérarchiques manquantes et extraction du niveau principal
    df_temp = df_temp.withColumn(
        "category_code",
        when(
            col("category_code").isNull() | (col("category_code") == ""),
            "unknown"
        ).otherwise(split(col("category_code"), "\\.")[0])
    )
    # Imputation intelligente des marques basée sur la catégorie
    df_temp = df_temp.withColumn(
        "brand",
        when(col("brand").isNull() | (col("brand") == ""),
            coalesce(
                first("brand").over(Window.partitionBy("category_code").orderBy("event_time")), # Use orderBy for deterministic first value
                lit("generic")
            )
        ).otherwise(col("brand"))
    )
    # 3. Nettoyage des prix (valeurs négatives ou nulles)
    logger.info("Nettoyage des prix")
    # Calcul des quartiles pour définir une plage de prix "normale"
    price_quantiles = df_temp.approxQuantile("price", [0.25, 0.75], 0.01)
    q1 = price_quantiles[0] if price_quantiles else None
    q3 = price_quantiles[1] if price_quantiles else None
    avg_price_by_category = df_temp.groupBy("category_code").agg(avg("price").alias("avg_cat_price"))
    df_temp = df_temp.join(avg_price_by_category, on="category_code", how="left")
    if q1 is not None and q3 is not None:
        lower_bound = q1 * 0.1
        upper_bound = q3 * 10
        df_temp = df_temp.withColumn("price",
            when(col("price").isNull() | (col("price") <= 0), col("avg_cat_price")) # Impute null/zero with category avg
            .when((col("price") >= lower_bound) & (col("price") <= upper_bound), col("price")) # Keep values within bounds
            .otherwise(col("avg_cat_price"))
        )
    else:
         df_temp = df_temp.withColumn("price",
            when(col("price").isNull() | (col("price") <= 0), col("avg_cat_price")) # Impute null/zero with category avg
            .otherwise(col("price"))
        )
    df_temp = df_temp.drop("avg_cat_price")
    logger.info("Aperçu des données prétraitées:")
    df_temp.show(5)
    logger.info(f"Distribution des prix après nettoyage :\n"
                f"- Min: {df_temp.select(min('price')).first()[0]}\n"
                f"- Max: {df_temp.select(max('price')).first()[0]}\n"
                f"- Médiane: {df_temp.select(percentile_approx('price', 0.5)).first()[0]}")
    logger.info("Statistiques après prétraitement:")
    df_temp.describe().show()
    return df_temp
def compute_user_behavior(cleaned_df):
    if cleaned_df is None:
        logger.error("Les données n'ont pas été prétraitées")
        return None
    logger.info("Calcul des métriques de comportement utilisateur")
    max_date = cleaned_df.select(max("event_time")).first()[0]
    user_behavior_df = cleaned_df.groupBy("user_id").agg(
        count("*").alias("nb_events"),
        sum(when(col("event_type") == "view", 1).otherwise(0)).alias("nb_views"),
        sum(when(col("event_type") == "cart", 1).otherwise(0)).alias("nb_carts"),
        sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("nb_purchases"),
        sum(when(col("event_type") == "remove_from_cart", 1).otherwise(0)).alias("nb_removes"),
        avg("price").alias("avg_price"),
        avg(when(col("event_type") == "purchase", col("price")).otherwise(None)).alias("avg_price_purchased"),
        countDistinct("user_session").alias("nb_sessions"),
        min("event_time").alias("first_seen"),
        max("event_time").alias("last_seen"),
        datediff(lit(max_date), max("event_time")).alias("recency"),
        countDistinct(when(col("event_type") == "purchase", col("date")).otherwise(None)).alias("frequency"),
        sum(when(col("event_type") == "purchase", col("price")).otherwise(0)).alias("monetary"),
        countDistinct("product_id").alias("unique_products"),
        countDistinct("category_code").alias("unique_categories"),
        countDistinct("brand").alias("unique_brands"),
        collect_list(when(col("event_type") == "view", col("category_code")).otherwise(None)).alias("viewed_categories"),
        collect_list(when(col("event_type") == "view", col("brand")).otherwise(None)).alias("viewed_brands")
    )
    user_behavior_df = user_behavior_df.withColumn(
        "main_category",
        expr("filter(viewed_categories, x -> x is not null)[0]")
    )
    user_behavior_df = user_behavior_df.withColumn(
        "conversion_rate",
        when(col("nb_views") > 0, col("nb_purchases") / col("nb_views")).otherwise(0)
    )
    user_behavior_df = user_behavior_df.withColumn(
        "cart_abandonment",
        when(col("nb_carts") > 0, (col("nb_carts") - col("nb_purchases")) / col("nb_carts")).otherwise(0)
    )
    user_behavior_df = user_behavior_df.withColumn(
        "engagement_days",
        datediff(col("last_seen"), col("first_seen")) + 1
    )

    # Calcul du score RFM composite pour compatibilité avec model_training.py
    user_behavior_df = user_behavior_df.withColumn(
        "rfm_score",
        (100 - col("recency")) * 0.3 +
        col("frequency") * 0.3 +
        (col("monetary") / 100) * 0.4  # Normalisation simple du monetary
    )

    logger.info("Métriques de comportement utilisateur calculées")
    logger.info("Aperçu des comportements utilisateur:")
    user_behavior_df.show(5)
    
    return user_behavior_df
def prepare_recommendation_data(cleaned_df):
    if cleaned_df is None:
        logger.error("Les données n'ont pas été prétraitées")
        return None, None
    logger.info("Préparation des données pour le système de recommandation")
    # 1. Normalisation des identifiants utilisateur et produit pour les modèles
    indexers = [
        StringIndexer(inputCol="user_id", outputCol="user_idx", handleInvalid="keep"),
        StringIndexer(inputCol="product_id", outputCol="product_idx", handleInvalid="keep")
    ]
    pipeline = Pipeline(stages=indexers)
    indexed_df = pipeline.fit(cleaned_df).transform(cleaned_df)
    # 2. DataFrame pour le filtrage collaboratif (ALS) avec IDs normalisés
    recommandation_df = indexed_df.filter(col("event_type").isin(["view", "cart", "purchase"])).select(
        "user_id",       # Inclure l'ID utilisateur original
        "user_idx",
        "product_id",    # Inclure l'ID produit original
        "product_idx",
        "event_type",
        "price",
        "event_time",
        # Score implicite basé sur l'interaction
        when(col("event_type") == "view", 1)
        .when(col("event_type") == "cart", 5)
        .when(col("event_type") == "purchase", 10)
        .otherwise(0).alias("interaction_score")
    )
    # 3. Calcul de la popularité des produits basée sur les événements
    logger.info("Calcul de la popularité des produits...")
    product_popularity_df = indexed_df.groupBy("product_idx").agg(
        count("*").alias("total_events"),
        sum(when(col("event_type") == "view", 1).otherwise(0)).alias("total_views"),
        sum(when(col("event_type") == "cart", 1).otherwise(0)).alias("total_carts"),
        sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("total_purchases"),
        countDistinct("user_id").alias("unique_users"), # Nombre d'utilisateurs uniques ayant interagi
        avg("price").alias("avg_price"),
        sum("price").alias("total_revenue")
    )
    logger.info("Popularité des produits calculée.")
    # 4. DataFrame des produits pour les recommandations basées sur le contenu avec agrégation des métadonnées
    product_metadata_df = indexed_df.groupBy("product_idx").agg(
        first("product_id").alias("product_id"), # Garder l'ID original si nécessaire
        mode("category_id").alias("main_category_id"),
        mode("category_code").alias("main_category_code"),
        mode("brand").alias("main_brand")
    )
    product_df = product_metadata_df.join(product_popularity_df, on="product_idx", how="left")
    product_df = product_df.select(
        "product_idx", 
        "product_id", 
        "main_category_id", 
        "main_category_code", 
        "main_brand", 
        "avg_price",
        "total_events",
        "total_views",
        "total_carts",
        "total_purchases",
        "unique_users",
        "total_revenue"
    )
    logger.info("Aperçu des données de recommandation:")
    recommandation_df.show(5)
    logger.info("Aperçu des données produits (avec popularité):")
    product_df.show(5)
    return recommandation_df, product_df
def prepare_time_series_data(cleaned_df):
    if cleaned_df is None:
        logger.error("Les données n'ont pas été prétraitées")
        return None
    logger.info("Préparation des données pour analyses temporelles")
    hourly_events = cleaned_df.groupBy("hour_bucket").agg(
        count("*").alias("total_events"),
        countDistinct("user_id").alias("unique_users"),
        sum(when(col("event_type") == "view", 1).otherwise(0)).alias("views"),
        sum(when(col("event_type") == "cart", 1).otherwise(0)).alias("carts"),
        sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("purchases"),
        sum(when(col("event_type") == "remove_from_cart", 1).otherwise(0)).alias("removes"),
        avg("price").alias("avg_price")
    ).orderBy("hour_bucket")
    logger.info("Aperçu des données temporelles:")
    hourly_events.show(5)
    return hourly_events
def save_processed_data(cleaned_df, user_behavior_df=None, recommendation_df=None, 
                        product_df=None, time_series_df=None, output_dir=output_directory):
    if cleaned_df is None:
        logger.error("Les données n'ont pas été prétraitées")
        return None
    output_dir = os.path.abspath(output_dir).replace("\\", "/")
    parquet_dir = os.path.join(output_dir, "parquet").replace("\\", "/")
    os.makedirs(parquet_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_paths = {
        "cleaned_data": f"{parquet_dir}/cleaned_data_{timestamp_str}.parquet",
        "user_behavior": f"{parquet_dir}/user_behavior_{timestamp_str}.parquet" if user_behavior_df is not None else None,
        "recommendation_data": f"{parquet_dir}/recommendation_data_{timestamp_str}.parquet" if recommendation_df is not None else None,
        "product_data": f"{parquet_dir}/product_data_{timestamp_str}.parquet" if product_df is not None else None,
        "time_series_data": f"{parquet_dir}/time_series_data_{timestamp_str}.parquet" if time_series_df is not None else None
    }
    logger.info(f"Sauvegarde des données nettoyées: {output_paths['cleaned_data']}")
    try:
        cleaned_df.write.partitionBy("date", "event_type").mode("overwrite").format("parquet").save(output_paths["cleaned_data"])
        logger.info("Données nettoyées sauvegardées")
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde des données nettoyées: {str(e)}")
    if user_behavior_df is not None:
        logger.info(f"Sauvegarde des comportements utilisateur: {output_paths['user_behavior']}")
        try:
            if "main_category" in user_behavior_df.columns:
                 user_behavior_df.write.partitionBy("main_category").mode("overwrite").format("parquet").save(output_paths["user_behavior"])
                 logger.info("Comportements utilisateur sauvegardés (partitionnés par main_category)")
            else:
                 user_behavior_df.write.mode("overwrite").format("parquet").save(output_paths["user_behavior"])
                 logger.info("Comportements utilisateur sauvegardés (sans partitionnement)")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des comportements utilisateur: {str(e)}")
    
    if recommendation_df is not None:
        logger.info(f"Sauvegarde des données de recommandation: {output_paths['recommendation_data']}")
        try:
            recommendation_df.write.mode("overwrite").format("parquet").save(output_paths["recommendation_data"])
            logger.info("Données de recommandation sauvegardées")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des données de recommandation: {str(e)}")
    if product_df is not None:
        logger.info(f"Sauvegarde des données produits: {output_paths['product_data']}")
        try:
            product_df.write.mode("overwrite").format("parquet").save(output_paths["product_data"])
            logger.info("Données produits sauvegardées")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des données produits: {str(e)}")
    if time_series_df is not None:
        logger.info(f"Sauvegarde des données temporelles: {output_paths['time_series_data']}")
        try:
            time_series_df.write.mode("overwrite").format("parquet").save(output_paths["time_series_data"])
            logger.info("Données temporelles sauvegardées")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des données temporelles: {str(e)}")
    
    logger.info(f"Toutes les données ont été sauvegardées dans {output_dir}")
    return output_paths
def main():
    # Création de la session Spark
    spark = create_spark_session()
    # Chargement des données
    raw_df = load_data(spark)
    #visualisation des données
    explore_data(raw_df)
    # Nettoyage et prétraitement
    cleaned_df = preprocess_data(raw_df)
    # Calcul des métriques utilisateur pour segmentation
    user_behavior_df = compute_user_behavior(cleaned_df)
    # Préparation des données pour recommandation
    recommendation_df, product_df = prepare_recommendation_data(cleaned_df)
    # Préparation des données temporelles pour simulation
    time_series_df = prepare_time_series_data(cleaned_df)
    save_processed_data(
        cleaned_df=cleaned_df,
        user_behavior_df=user_behavior_df,
        recommendation_df=recommendation_df,
        product_df=product_df,
        time_series_df=time_series_df
    )
    logger.info("Pipeline de prétraitement terminé avec succès")
    # Arrêt de la session Spark
    spark.stop()

# Si exécuté comme script principal
if __name__ == "__main__":
    main()