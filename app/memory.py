"""Pick the LangGraph checkpointer ("short-term memory") from env. Same code in every environment.

MEMORY_BACKEND = memory     in-process, lost when the session ends (first runtime smoke test)
                 postgres   PostgresSaver on DATABASE_URL (local Docker, RDS/Aurora, or Lakebase)
                 agentcore  AgentCoreMemorySaver on AGENTCORE_MEMORY_ID (practice only; platform may not allow it)
"""
import os


def get_checkpointer():
    kind = os.getenv("MEMORY_BACKEND", "memory")
    if kind == "memory":
        from langgraph.checkpoint.memory import InMemorySaver
        return InMemorySaver()
    if kind == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool
        pool = ConnectionPool(os.environ["DATABASE_URL"], max_size=int(os.getenv("DB_POOL_MAX", "4")),
                              kwargs={"autocommit": True}, open=True)
        saver = PostgresSaver(pool)
        if os.getenv("DB_SETUP", "0") == "1":  # run once per environment, not on every start
            saver.setup()
        return saver
    if kind == "agentcore":
        from langgraph_checkpoint_aws import AgentCoreMemorySaver
        return AgentCoreMemorySaver(os.environ["AGENTCORE_MEMORY_ID"],
                                    region_name=os.getenv("AWS_REGION", "us-east-1"))
    raise ValueError(f"unknown MEMORY_BACKEND {kind}")
