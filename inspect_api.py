import requests
import json

url = "https://transport.opendata.ch/v1/connections"
params = {'from': 'Zurich HB', 'to': 'Bern', 'limit': 1}

resp = requests.get(url, params=params)
data = resp.json()

conn = data['connections'][0]

print("=== DEPARTURE (from) ===")
dep = conn['from']
print(f"departure (planned): {dep.get('departure')}")
print(f"delay: {dep.get('delay')}")
print(f"prognosis: {dep.get('prognosis')}")

print("\n=== ARRIVAL (to) ===")
arr = conn['to']
print(f"arrival (planned): {arr.get('arrival')}")
print(f"delay: {arr.get('delay')}")
print(f"prognosis: {arr.get('prognosis')}")

print("\n=== SECTIONS (detailed journey) ===")
for i, section in enumerate(conn.get('sections', [])):
    if section.get('journey'):
        print(f"\nSection {i}:")
        print(f"  departure: {section.get('departure')}")
        print(f"  arrival: {section.get('arrival')}")
