#main recommendations
import json
import os

def load_pois():
    data_path = os.path.join(os.path.dirname(__file__), "data", "sample_pois.json")
    with open(data_path, "r") as f:
        return json.load(f)

def get_recommendations(preferences):
    pois = load_pois()
    vibes = preferences.get("vibes", [])
    budget = preferences.get("budget", "medium")

    scored_pois = []
    for poi in pois:
        score = 0
        if poi["budget"] == budget:
            score += 1
        score += len(set(poi["tags"]) & set(vibes))
        scored_pois.append((poi, score))

    ranked = sorted(scored_pois, key=lambda x: x[1], reverse=True)
    recommendations = [
        {"name": poi["name"], "reason": f"Matches your {', '.join(vibes)} preferences; popular spot!"}
        for poi, _ in ranked if _ > 0
    ]

    return recommendations if recommendations else [{"name": "No matches found", "reason": "Try adjusting preferences."}]
