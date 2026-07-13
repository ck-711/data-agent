from dataclasses import asdict

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct
from watchfiles import awatch

from app.conf.app_config import app_config
from app.entities.metric_info import MetricInfo


class MetricQdrantRepository:
    coll_name = "data-agent-metric"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def ensure_collection(self):
        if not await self.client.collection_exists(collection_name=self.coll_name):
            await self.client.create_collection(
                collection_name=self.coll_name,
                vectors_config=VectorParams(
                    size=app_config.qdrant.embedding_size,
                    distance=Distance.COSINE
                )
            )

    async def upsert(self, ids:list[str], payloads:list[MetricInfo], embeddings:list[list[float]], batch_size:int=20):
        # [(向量ID,业务数据,向量值),()]
        zipped = list(zip(ids, payloads, embeddings))
        #分批次处理
        for i in  range(0, len(zipped), batch_size):
            batch = zipped[i:i+batch_size]
            points = [PointStruct(
                id=id,
                vector=embedding,
                payload=asdict(payload)
            ) for id,payload,embedding in batch]
            await self.client.upsert(collection_name=self.coll_name, points=points)

    async def search(self, embedding:list[float], score_threshold: float = 0.6, limit: int = 10):
        result = await self.client.query_points(
            collection_name=self.coll_name,
            query=embedding,
            score_threshold=score_threshold,
            limit=limit
        )
        return [MetricInfo(**point.payload) for point in result.points]
