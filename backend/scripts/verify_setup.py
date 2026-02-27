#!/usr/bin/env python3
"""Verify all credentials and connections for CatalogSentinel."""
import os, sys, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

async def main():
    print("\nCatalogSentinel — Setup Verification\n")

    # Elasticsearch
    try:
        from es.client import get_async_es
        es = get_async_es()
        info = await es.info()
        print(f"✅ Elasticsearch {info['version']['number']}")
        await es.close()
    except Exception as e:
        print(f"❌ Elasticsearch: {e}")

    # Kibana
    try:
        from kibana.agent_client import get_agent_client
        client = get_agent_client()
        agents = await client.check_all_agents()
        ok = sum(1 for v in agents.values() if v)
        print(f"{'✅' if ok > 0 else '⚠️ '} Kibana Agents: {ok}/{len(agents)} available")
    except Exception as e:
        print(f"❌ Kibana: {e}")

    # Jina
    from config.settings import settings
    if settings.JINA_API_KEY:
        try:
            from multilingual.jina_embeddings import JinaEmbeddings
            j = JinaEmbeddings()
            emb = await j.generate_embedding("test")
            print(f"✅ Jina embeddings: dim={len(emb) if emb else 0}")
        except Exception as e:
            print(f"❌ Jina: {e}")
    else:
        print("⚠️  Jina API key not set — vector search disabled")

    # Slack
    if settings.slack_webhooks:
        print(f"✅ Slack webhooks: {list(settings.slack_webhooks.keys())}")
    else:
        print("⚠️  Slack not configured")

    # Jira
    if settings.JIRA_URL and settings.JIRA_API_TOKEN:
        print(f"✅ Jira: {settings.JIRA_URL}")
    else:
        print("⚠️  Jira not configured")

    print("\nDone.")

asyncio.run(main())
