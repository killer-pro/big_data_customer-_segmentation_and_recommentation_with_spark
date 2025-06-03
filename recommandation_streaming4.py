import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, lit, desc, row_number, count, broadcast,
    when, sum as spark_sum, window, split
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType,
    TimestampType, IntegerType, LongType, DecimalType
)
from pyspark.sql.window import Window
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUXDB_CONFIG = {
    "url": "http://localhost:8086",
    "token": "unnKev8Hl5N-Puf6-yGkVCvFH9FVrI9fqh01UfSFvezpaClqnZTWPYRXMScM_3hPQoUxRmgnrTaTd0qBZyPrxQ==",
    "org": "self",
    "bucket": "spark_customer_recommandation"
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

schema = StructType([
    StructField("event_time", TimestampType(), True),
    StructField("event_type", StringType(), True),
    StructField("product_id", LongType(), True),
    StructField("category_id", DecimalType(38, 0), True),
    StructField("category_code", StringType(), True),
    StructField("brand", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("user_id", StringType(), True),
    StructField("user_session", StringType(), True)
])


class StreamingRecommendationSystem:
    def __init__(self):
        self.spark = self._create_spark_session()
        self.product_popularity = self._load_product_popularity()
        self.user_preferences = {}

    def _create_spark_session(self):
        return SparkSession.builder \
            .appName("Streaming Recommendation System") \
            .config("spark.driver.memory", "8g") \
            .config("spark.executor.memory", "8g") \
            .config("spark.sql.streaming.checkpointLocation", "./checkpoint") \
            .master("local[*]") \
            .getOrCreate()

    def _load_product_popularity(self):
        try:
            df = self.spark.read.parquet("./data/processed/parquet/product_data_*.parquet")
            return df.select("product_id", "total_purchases", "avg_price", "main_category_code", "main_brand") \
                .orderBy(desc("total_purchases"))
        except:
            logger.warning("Product data not found, using empty DataFrame")
            return self.spark.createDataFrame([], schema=StructType([
                StructField("product_id", LongType(), True),
                StructField("total_purchases", IntegerType(), True),
                StructField("avg_price", DoubleType(), True),
                StructField("main_category_code", StringType(), True),
                StructField("main_brand", StringType(), True)
            ]))

    def _write_to_influxdb(self, df, measurement_name):
        def write_batch(batch_df, batch_id):
            try:
                client = InfluxDBClient(
                    url=INFLUXDB_CONFIG["url"],
                    token=INFLUXDB_CONFIG["token"],
                    org=INFLUXDB_CONFIG["org"]
                )
                write_api = client.write_api(write_options=SYNCHRONOUS)

                points = []
                for row in batch_df.collect():
                    point = Point(measurement_name)
                    for field in row.asDict():
                        if field == "event_time":
                            point = point.time(row[field])
                        elif isinstance(row[field], (int, float)):
                            point = point.field(field, row[field])
                        else:
                            point = point.tag(field, str(row[field]))
                    points.append(point)

                if points:
                    write_api.write(bucket=INFLUXDB_CONFIG["bucket"], record=points)
                    logger.info(f"Written {len(points)} {measurement_name} points to InfluxDB")

                write_api.close()
                client.close()

            except Exception as e:
                logger.error(f"Error writing to InfluxDB: {e}")

        return write_batch

    def _generate_recommendations(self, user_activity_df, batch_id):
        try:
            # Extraire le niveau principal de la catégorie du code de catégorie du flux
            user_activity_df_processed = user_activity_df.withColumn(
                "main_category",
                when(
                    col("category_code").isNull() | (col("category_code") == ""),
                    "unknown"
                ).otherwise(split(col("category_code"), "\\.")[0])
            )
            logger.info(f"Batch {batch_id}: user_activity_df_processed count = {user_activity_df_processed.count()}")

            user_interactions = user_activity_df_processed.groupBy("user_id", "product_id") \
                .agg(
                count("*").alias("interaction_count"),
                spark_sum(when(col("event_type") == "view", 1).otherwise(0)).alias("views"),
                spark_sum(when(col("event_type") == "cart", 1).otherwise(0)).alias("carts"),
                spark_sum(when(col("event_type") == "purchase", 1).otherwise(0)).alias("purchases")
            )
            # user_interactions.printSchema()
            logger.info(f"Batch {batch_id}: user_interactions count = {user_interactions.count()}")

            user_categories = user_activity_df_processed.filter(col("category_code").isNotNull()) \
                .groupBy("user_id", "main_category") \
                .agg(count("*").alias("category_interest"))
            # user_categories.printSchema()
            logger.info(f"Batch {batch_id}: user_categories count = {user_categories.count()}")

            top_categories = user_categories.withColumn(
                "rank", row_number().over(Window.partitionBy("user_id").orderBy(desc("category_interest")))
            ).filter(col("rank") <= 3)

            recommendations = top_categories.join(
                broadcast(self.product_popularity.filter(col("total_purchases") > 0)),
                on=top_categories.main_category == self.product_popularity.main_category_code, how="inner"
            ).withColumn(
                "rec_score",
                col("category_interest") * col("total_purchases") / 100
            ).withColumn(
                "rank", row_number().over(Window.partitionBy("user_id").orderBy(desc("rec_score")))
            )
            # recommendations.printSchema()
            logger.info(f"Batch {batch_id}: recommendations before rank filter count = {recommendations.count()}")

            # Fallback mechanism: if collaborative recommendations are empty, recommend top popular products
            if recommendations.isEmpty():
                logger.warning(f"Batch {batch_id}: Collaborative recommendations are empty. Falling back to popular products.")
                # Get unique users from the current batch
                # Note: Use user_activity_df_processed here as it includes the users from the batch
                unique_users_df = user_activity_df_processed.select("user_id").distinct()

                # Get top 10 popular products (globally from loaded data)
                top_popular_products = self.product_popularity

                # Assign top popular products to all users in the batch
                fallback_recommendations = unique_users_df.crossJoin(top_popular_products.limit(10))

                # Select and rename columns to match the schema of regular recommendations
                # Ensure main_category is selected as recommended_category_code for consistency
                recommendations = fallback_recommendations.select(
                    col(unique_users_df.user_id).alias("user_id"),
                    col(top_popular_products.product_id).alias("product_id"),
                    lit(0.1).alias("rec_score"),
                    col(top_popular_products.main_category_code).alias("recommended_category_code"), # Use main_category_code from product data
                    col(top_popular_products.main_brand).alias("main_brand"),
                    col(top_popular_products.avg_price).alias("avg_price")
                ).withColumn("recommendation_type", lit("streaming_popular_fallback"))

                logger.info(f"Batch {batch_id}: Fallback recommendations count = {recommendations.count()}")

            else:
                recommendations = recommendations.filter(col("rank") <= 5) \
                    .select(
                    "user_id", "product_id", "rec_score", col("main_category").alias("recommended_category_code"),
                    "main_brand", "avg_price"
                ).withColumn("recommendation_type", lit("streaming_collaborative"))

            return recommendations

        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return None

    def start_streaming(self, input_path="../data/novembre"):
        logger.info(f"Starting streaming from {input_path}")

        stream_df = self.spark.readStream \
            .format("csv") \
            .option("header", "true") \
            .schema(schema) \
            .option("maxFilesPerTrigger", 1) \
            .load(input_path)

        windowed_activity = stream_df \
            .withWatermark("event_time", "10 minutes") \
            .groupBy(
            window(col("event_time"), "5 minutes"),
            "user_id", "product_id", "event_type", "category_code", "brand", "price"
        ).agg(count("*").alias("event_count"))

        def process_batch(batch_df, batch_id):
            if batch_df.isEmpty():
                return

            logger.info(f"Processing batch {batch_id}")

            current_activity = batch_df.select(
                "user_id", "product_id", "event_type", "category_code", "brand", "price"
            )
            logger.info(f"Batch {batch_id}: current_activity count = {current_activity.count()}")
            # current_activity.printSchema()

            self._write_to_influxdb(current_activity, "user_events")(current_activity, batch_id)

            recommendations = self._generate_recommendations(current_activity, batch_id)
            if recommendations and not recommendations.isEmpty():
                self._write_to_influxdb(recommendations, "recommendations")(recommendations, batch_id)

                # Sauvegarder les recommandations dans un fichier CSV
                output_csv_path = "./results/streaming_recommendations/"
                logger.info(f"Batch {batch_id}: Saving recommendations to CSV in {output_csv_path}")
                try:
                    # Use mode("append") to add results from each batch
                    recommendations.write.mode("append").option("header", "true").csv(output_csv_path)
                    logger.info(f"Batch {batch_id}: Recommendations saved to CSV.")
                except Exception as e:
                    logger.error(f"Batch {batch_id}: Error saving recommendations to CSV: {e}")

        query = windowed_activity.writeStream \
            .outputMode("update") \
            .foreachBatch(process_batch) \
            .trigger(processingTime='60 seconds') \
            .start()

        try:
            query.awaitTermination()
        except KeyboardInterrupt:
            logger.info("Stopping streaming...")
            query.stop()
            self.spark.stop()


def main():
    system = StreamingRecommendationSystem()
    system.start_streaming()


if __name__ == "__main__":
    main()