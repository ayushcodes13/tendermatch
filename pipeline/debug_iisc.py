import requests

URL = "https://iisc.ac.in/all-tenders/"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(URL, headers=headers, timeout=20)

print("STATUS:", response.status_code)
print("HTML LENGTH:", len(response.text))

text = response.text.lower()

target = "maskless laser lithography"

print("FOUND TARGET:", target in text)

if target in text:
    idx = text.find(target)
    print("\nSNIPPET:\n")
    print(response.text[idx-300:idx+500])
else:
    print("\nTarget not present in raw HTML")