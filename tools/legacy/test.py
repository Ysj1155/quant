import requests
from config import APP_KEY, APP_SECRET, ACCOUNT_NO
import http.client
import json

conn = http.client.HTTPSConnection("openapivts.koreainvestment.com", 29443)
payload = json.dumps({
  "grant_type": "client_credentials",
  "appkey": APP_KEY,
  "appsecret": APP_SECRET
})
headers = {
  'content-type': "application/json; charset=UTF-8"
}
conn.request("POST", "/oauth2/tokenP", payload, headers)
res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))
