import urllib.request
import urllib.parse
import json
import time

GOOGLE_MAPS_KEY = "AIzaSyCqDfKzOW_fYVnhTBnQQPPFcIwFr7q2nCU"

hospitals = [
    {"name": "Bellevue Hospital Center", "address": "462 First Avenue, New York, NY 10016", "phone": "(212) 562-4132", "borough": "Manhattan"},
    {"name": "Harlem Hospital Center", "address": "506 Lenox Avenue, New York, NY 10037", "phone": "(212) 939-1000", "borough": "Manhattan"},
    {"name": "Metropolitan Hospital Center", "address": "1901 First Avenue, New York, NY 10029", "phone": "(212) 423-8993", "borough": "Manhattan"},
    {"name": "Mount Sinai Hospital", "address": "One Gustave L Levy Place, New York, NY 10029", "phone": "(212) 241-7005", "borough": "Manhattan"},
    {"name": "Mount Sinai Morningside", "address": "1111 Amsterdam Avenue, New York, NY 10025", "phone": "(212) 523-4295", "borough": "Manhattan"},
    {"name": "NewYork-Presbyterian Columbia", "address": "622 West 168th Street, New York, NY 10032", "phone": "(212) 305-2500", "borough": "Manhattan"},
    {"name": "NewYork-Presbyterian Weill Cornell", "address": "525 East 68th Street, New York, NY 10021", "phone": "(212) 746-5454", "borough": "Manhattan"},
    {"name": "Northwell Greenwich Village Hospital", "address": "30 Seventh Avenue, New York, NY 10011", "phone": "(516) 465-8018", "borough": "Manhattan"},
    {"name": "Kings County Hospital Center", "address": "451 Clarkson Avenue, Brooklyn, NY 11203", "phone": "(718) 245-3901", "borough": "Brooklyn"},
    {"name": "NewYork-Presbyterian Brooklyn Methodist", "address": "506 Sixth Street, Brooklyn, NY 11215", "phone": "(718) 780-3101", "borough": "Brooklyn"},
    {"name": "NYU Langone Hospital Brooklyn", "address": "150 55th Street, Brooklyn, NY 11220", "phone": "(718) 630-7300", "borough": "Brooklyn"},
    {"name": "South Brooklyn Health", "address": "2601 Ocean Parkway, Brooklyn, NY 11235", "phone": "(718) 616-3000", "borough": "Brooklyn"},
    {"name": "Woodhull Medical Center", "address": "760 Broadway, Brooklyn, NY 11206", "phone": "(718) 963-8101", "borough": "Brooklyn"},
    {"name": "Elmhurst Hospital Center", "address": "79-01 Broadway, Elmhurst, NY 11373", "phone": "(718) 334-4000", "borough": "Queens"},
    {"name": "NewYork-Presbyterian Queens", "address": "56-45 Main Street, Flushing, NY 11355", "phone": "(718) 670-2000", "borough": "Queens"},
    {"name": "Queens Hospital Center", "address": "82-68 164th Street, Jamaica, NY 11432", "phone": "(718) 883-2350", "borough": "Queens"},
    {"name": "Jacobi Medical Center", "address": "1400 Pelham Parkway, Bronx, NY 10461", "phone": "(718) 918-5000", "borough": "Bronx"},
    {"name": "Lincoln Medical Center", "address": "234 East 149th Street, Bronx, NY 10451", "phone": "(718) 579-5700", "borough": "Bronx"},
    {"name": "North Central Bronx Hospital", "address": "3424 Kossuth Avenue, Bronx, NY 10467", "phone": "(718) 519-3500", "borough": "Bronx"},
    {"name": "Richmond University Medical Center", "address": "355 Bard Avenue, Staten Island, NY 10310", "phone": "(718) 818-1234", "borough": "Staten Island"},
]

results = []
for h in hospitals:
    encoded = urllib.parse.quote(h['address'])
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded}&key={GOOGLE_MAPS_KEY}"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            if data['results']:
                loc = data['results'][0]['geometry']['location']
                h['lat'] = loc['lat']
                h['lng'] = loc['lng']
                print(f"✓ {h['name']}: {loc['lat']}, {loc['lng']}")
            else:
                print(f"✗ {h['name']}: no results")
    except Exception as e:
        print(f"✗ {h['name']}: {e}")
    results.append(h)
    time.sleep(0.1)

with open("hospitals_with_coords.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nDone! Saved to hospitals_with_coords.json")