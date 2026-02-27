#!/usr/bin/env python3
"""
Inject anomalous decisions to trigger drift detection.
"""
import requests
from datetime import datetime, timedelta
import random

API_URL = "http://localhost:8000"

def inject_drift_for_algorithm(algorithm="zomato_surge_pricing", count=50):
    """Inject decisions with anomalous distribution to trigger drift."""
    print(f"🔥 Injecting {count} anomalous decisions for {algorithm}...")
    
    decisions = []
    now = datetime.utcnow()
    
    # Create anomalous distribution - mostly HIGH instead of normal mix
    for i in range(count):
        timestamp = (now - timedelta(minutes=random.randint(0, 25))).isoformat()
        
        # 90% HIGH (normally 54%), 5% LOW, 5% MEDIUM - extreme drift!
        category = random.choices(
            ["HIGH", "LOW", "MEDIUM", "EXTREME"],
            weights=[70, 10, 10, 10]  # Add new category + shift distribution
        )[0]
        
        decision = {
            "decision_id": f"DRIFT-{i+1:05d}",
            "algorithm": algorithm,
            "version": "1.0",
            "company": "Zomato",
            "platform": "app",
            "input_features": {
                "demand": random.randint(80, 100),  # High demand
                "supply": random.randint(5, 15),    # Low supply
                "time_of_day": "dinner",
            },
            "output": {
                "category": category,
                "value": 2.5 if category == "HIGH" else 1.2,
                "price": 500
            },
            "location": {
                "zone": random.choice(["north", "south", "west", "east"]),
                "city": "Delhi"
            },
            "timestamp": timestamp
        }
        decisions.append(decision)
    
    # Post bulk
    try:
        response = requests.post(
            f"{API_URL}/api/drift/decisions/bulk",
            json={"decisions": decisions},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Injected: {result.get('indexed', 0)} anomalous decisions")
            
            # Now check for drift
            print(f"\n🔍 Checking for drift on {algorithm}...")
            check_response = requests.post(
                f"{API_URL}/api/drift/check/{algorithm}",
                timeout=30
            )
            
            if check_response.status_code == 200:
                drift_result = check_response.json()
                if drift_result.get("drift_detected"):
                    print(f"\n🚨 DRIFT DETECTED!")
                    print(f"   KL Divergence: {drift_result.get('incident', {}).get('kl_divergence')}")
                    print(f"   Revenue Impact: ₹{drift_result.get('incident', {}).get('revenue_impact_inr', 0):,.0f}")
                    print(f"   Incident ID: {drift_result.get('incident', {}).get('incident_id')}")
                    print(f"\n✅ Workflow triggered:")
                    print(f"   Actions: {drift_result.get('workflow', {}).get('actions', [])}")
                else:
                    debug = drift_result.get("debug", {})
                    print(f"\n⚠️  No drift detected yet")
                    print(f"   KL Divergence: {debug.get('kl_divergence')} (threshold: {debug.get('threshold')})")
                    print(f"   Current: {debug.get('current_dist')}")
                    print(f"   Baseline: {debug.get('baseline_dist')}")
            else:
                print(f"❌ Drift check failed: {check_response.status_code}")
                print(check_response.text)
        else:
            print(f"❌ Failed to inject: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("  CatalogSentinel — Drift Injection Test")
    print("=" * 60)
    print()
    
    inject_drift_for_algorithm("zomato_surge_pricing", count=100)
    
    print()
    print("=" * 60)
    print("🌐 Check dashboard: http://localhost:5173")
    print("📊 View incidents: http://localhost:8000/api/drift/incidents")
    print("=" * 60)
