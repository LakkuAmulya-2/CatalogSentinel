#!/usr/bin/env python3
"""
Populate CatalogSentinel with test data for dashboard testing.
"""
import requests
import random
from datetime import datetime, timedelta

API_URL = "http://localhost:8000"

# Sample algorithms - including zomato_surge_pricing
ALGORITHMS = ["zomato_surge_pricing", "surge_pricing", "dynamic_discount", "inventory_optimizer", "recommendation_engine"]

# Sample locations
LOCATIONS = [
    {"zone": "north", "city": "Delhi", "lat": 28.7041, "lon": 77.1025},
    {"zone": "south", "city": "Bangalore", "lat": 12.9716, "lon": 77.5946},
    {"zone": "west", "city": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    {"zone": "east", "city": "Kolkata", "lat": 22.5726, "lon": 88.3639},
]


def generate_decisions(count=200):
    """Generate sample algorithm decisions."""
    decisions = []
    now = datetime.utcnow()
    
    for i in range(count):
        # Random timestamp in last 24 hours
        timestamp = (now - timedelta(minutes=random.randint(0, 1440))).isoformat()
        
        algorithm = random.choice(ALGORITHMS)
        location = random.choice(LOCATIONS)
        
        # Generate output based on algorithm
        if "surge" in algorithm:
            multiplier = round(random.uniform(1.0, 2.5), 2)
            output = {
                "category": "surge" if multiplier > 1.5 else "normal",
                "value": multiplier,
                "price": 200 * multiplier
            }
        elif algorithm == "dynamic_discount":
            discount = round(random.uniform(0, 50), 1)
            output = {
                "category": f"{int(discount//10)*10}%_off",
                "value": discount,
                "final_price": 1000 * (1 - discount/100)
            }
        elif algorithm == "inventory_optimizer":
            reorder = random.choice([True, False])
            output = {
                "category": "reorder" if reorder else "sufficient",
                "value": random.randint(10, 500),
                "action": "reorder" if reorder else "none"
            }
        else:  # recommendation_engine
            score = round(random.uniform(0.5, 1.0), 3)
            output = {
                "category": "high_relevance" if score > 0.8 else "medium_relevance",
                "value": score,
                "recommended": random.choice([True, False])
            }
        
        decision = {
            "decision_id": f"DEC-{algorithm[:4].upper()}-{i+1:05d}",
            "algorithm": algorithm,
            "version": "1.0",
            "company": "Zomato" if "zomato" in algorithm else "TestCorp",
            "platform": random.choice(["web", "app", "api"]),
            "input_features": {
                "demand": random.randint(10, 100),
                "supply": random.randint(5, 80),
                "time_of_day": random.choice(["breakfast", "lunch", "dinner", "late_night"]),
                "weather": random.choice(["sunny", "rainy", "cloudy"]),
            },
            "output": output,
            "location": location,
            "timestamp": timestamp
        }
        decisions.append(decision)
    
    return decisions


def post_decisions(decisions):
    """Post decisions to API."""
    print(f"📤 Posting {len(decisions)} decisions...")
    
    # Bulk post
    try:
        response = requests.post(
            f"{API_URL}/api/drift/decisions/bulk",
            json={"decisions": decisions},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Indexed: {result.get('indexed', 0)}, Failed: {result.get('failed', 0)}")
            return True
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error posting decisions: {e}")
        return False


def main():
    print("=" * 60)
    print("  CatalogSentinel — Test Data Population")
    print("=" * 60)
    print()
    
    # Check if API is running
    try:
        response = requests.get(f"{API_URL}/api/health", timeout=5)
        if response.status_code != 200:
            print("❌ API not responding. Make sure server is running on http://localhost:8000")
            return
        print("✅ API is running")
        print()
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        print("   Make sure to run: uvicorn api.main:app --reload")
        return
    
    # Generate and post decisions
    print("1️⃣  Generating algorithm decisions...")
    decisions = generate_decisions(200)
    
    # Show algorithm distribution
    algo_counts = {}
    for d in decisions:
        algo = d["algorithm"]
        algo_counts[algo] = algo_counts.get(algo, 0) + 1
    
    print(f"   Generated decisions by algorithm:")
    for algo, count in algo_counts.items():
        print(f"     - {algo}: {count}")
    print()
    
    post_decisions(decisions)
    print()
    
    print("=" * 60)
    print("✅ Test data populated successfully!")
    print()
    print("Now you can test drift detection:")
    print(f"  POST {API_URL}/api/drift/check/zomato_surge_pricing")
    print()
    print("🌐 Open dashboard: http://localhost:5173")
    print("📊 API docs: http://localhost:8000/docs")
    print("=" * 60)


if __name__ == "__main__":
    main()
